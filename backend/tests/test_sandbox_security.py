"""Module 6 — sandbox security tests, run against the REAL `executor`
container over Docker, never mocked. This is the one place in the whole
test suite that talks to real infrastructure instead of
FakeCodeExecutor — module §18/§24's explicit "run the security suite
against the actual sandbox, not a fake" requirement, and "do not claim a
security property that has not actually been tested."

Skipped automatically (not failed) when Docker isn't reachable, so the
rest of the suite never depends on it — mirrors this project's existing
"fake by default, real infra opt-in" pattern (docker_sandbox_available()
below is this file's equivalent of conftest.py's autouse fixtures).

**Container lifecycle**: docker-compose.yml's `executor` service
deliberately publishes no port at all (`- never reachable from the host`
— see its own comment) — that is itself a security property, and
`internal: true` on its network means Docker never sets up the NAT/
gateway plumbing a published port would need anyway (confirmed the hard
way — see below). So this file starts a SEPARATE, test-only container
from the same image, with every one of docker-compose.yml's hardening
flags reproduced exactly (`--read-only`, the same `tmpfs`/`cap-drop`/
`security-opt`, an `--internal` network, and — matching production
exactly rather than compromising on it — **no published port at all**.
The test harness talks to the container via `docker exec ... python3`,
hitting `localhost:8100` from *inside* the container's own network
namespace (`docker exec` uses the container's PID/net namespace
directly, entirely independent of whatever the container's network can
or can't route to) — never through a host-reachable port. First attempt
at this file genuinely did try `-p 127.0.0.1:PORT:8100` alongside
`--internal`, and it genuinely failed: `docker run` succeeds, uvicorn
logs "Uvicorn running on http://0.0.0.0:8100", but the published port
was never reachable from the host — an `internal: true` network has no
gateway/NAT infrastructure at all, which a published port depends on,
regardless of whether the container itself is listening. Real
information from actually running this, not assumed — see backend/
README.md's Module 6 section for the full account.

Every test below is a genuine claim about what the running sandbox does,
verified by actually doing it — not by reading the code and asserting it
should work.
"""

import json
import shutil
import subprocess
import time
import uuid
from collections.abc import Iterator

import pytest

_IMAGE_TAG = "interviewiq-executor-security-test"
_NETWORK_NAME = "interviewiq-sandbox-security-test-net"
_CONTAINER_NAME = "interviewiq-executor-security-test"

_HEALTH_CHECK_SCRIPT = (
    "import urllib.request; " "urllib.request.urlopen('http://localhost:8100/health', timeout=2)"
)

# Runs inside the container via `docker exec`, hitting its own loopback —
# never a published port (see module docstring). Reads the JSON request
# body from stdin, prints "<status_code>\n<json body>" to stdout. Every
# write goes through the same sys.stdout.buffer stream deliberately —
# mixing text-mode print() with binary buffer.write() here previously
# caused the two to flush in the wrong order (the buffered text write
# landing after the unbuffered binary one), corrupting the status-line/
# body split; caught by actually running this against the real container,
# not by reading the code.
_EXEC_SCRIPT = """
import sys, urllib.request, urllib.error
payload = sys.stdin.buffer.read()
req = urllib.request.Request(
    "http://localhost:8100/execute", data=payload, headers={"Content-Type": "application/json"}
)
try:
    with urllib.request.urlopen(req, timeout=60) as resp:
        sys.stdout.buffer.write(str(resp.status).encode() + b"\\n")
        sys.stdout.buffer.write(resp.read())
except urllib.error.HTTPError as e:
    sys.stdout.buffer.write(str(e.code).encode() + b"\\n")
    sys.stdout.buffer.write(e.read())
"""


def _docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        subprocess.run(["docker", "info"], capture_output=True, timeout=10, check=True)
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
        return False


_DOCKER_UP = _docker_available()

pytestmark = pytest.mark.skipif(
    not _DOCKER_UP,
    reason="Docker is not reachable — real-sandbox security tests are skipped, "
    "never faked (module §18). Start Docker Desktop to run this file.",
)


def _run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=120, **kwargs)


@pytest.fixture(scope="module", autouse=True)
def _executor_container() -> Iterator[None]:
    """Module-lifecycle for the test-only executor container — plain
    (non-async) generator fixture, setup/teardown around every test in
    this file, using the exact hardening flags docker-compose.yml applies
    to the real `executor` service (see the module docstring for why this
    can't just reuse the compose-managed one directly).
    """
    if not _DOCKER_UP:
        yield
        return

    build = _run(["docker", "build", "-t", _IMAGE_TAG, "./execution_worker"])
    assert build.returncode == 0, f"executor image build failed:\n{build.stderr}"

    # Best-effort cleanup of a stale run from a previous crashed session —
    # failure here is fine, there's nothing to clean up on a fresh run.
    _run(["docker", "rm", "-f", _CONTAINER_NAME])
    _run(["docker", "network", "rm", _NETWORK_NAME])

    net = _run(["docker", "network", "create", "--internal", _NETWORK_NAME])
    assert net.returncode == 0, f"failed to create internal test network:\n{net.stderr}"

    run = _run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            _CONTAINER_NAME,
            "--network",
            _NETWORK_NAME,
            "--read-only",
            "--tmpfs",
            # `exec` — matches docker-compose.yml's executor service; a
            # compiled C++ binary must be able to run from the same
            # scratch dir it was compiled into (Docker's tmpfs mounts
            # default to noexec, which silently broke every C++
            # submission — confirmed live, see docker-compose.yml's
            # comment for the full account).
            "/tmp:size=128m,mode=1777,exec",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges:true",
            # Matches docker-compose.yml's executor service exactly — a
            # container-level backstop on top of (not instead of)
            # sandbox_runner.py's per-process rlimits, closing the gap a
            # `docker inspect` on the real service once showed (no cgroup
            # limit at all, `Memory=0`/`NanoCpus=0`) before this was added.
            # 4g/256 (not the initial 2g/128) after empirically finding the
            # JVM's own RLIMIT_AS/RLIMIT_NPROC needs (languages.py). cpus=4.0
            # (not the initial 2.0) after a real `#include <bits/stdc++.h>`
            # compile measured too little margin under concurrent load at
            # 2.0 — see docker-compose.yml's executor service comment.
            "--memory",
            "4g",
            "--cpus",
            "4.0",
            "--pids-limit",
            "256",
            _IMAGE_TAG,
        ]
    )
    assert run.returncode == 0, f"failed to start test executor container:\n{run.stderr}"

    # Readiness check via `docker exec` (never a published port — module
    # docstring) — retried since the container needs a moment to bind its
    # port after `docker run -d` returns.
    healthy = False
    for _ in range(30):
        health = _run(["docker", "exec", _CONTAINER_NAME, "python3", "-c", _HEALTH_CHECK_SCRIPT])
        if health.returncode == 0:
            healthy = True
            break
        time.sleep(1)
    if not healthy:
        logs = _run(["docker", "logs", _CONTAINER_NAME])
        _run(["docker", "rm", "-f", _CONTAINER_NAME])
        _run(["docker", "network", "rm", _NETWORK_NAME])
        raise RuntimeError(
            f"executor test container never became healthy:\n{logs.stdout}\n{logs.stderr}"
        )

    yield

    _run(["docker", "rm", "-f", _CONTAINER_NAME])
    _run(["docker", "network", "rm", _NETWORK_NAME])


async def _execute(
    *,
    language: str,
    source_code: str,
    stdin: str = "",
    timeout_seconds: int = 6,
    memory_limit_mb: int = 128,
    max_output_bytes: int = 65536,
) -> dict:
    payload = {
        "language": language,
        "source_code": source_code,
        "inputs": [{"id": "t1", "stdin": stdin}],
        "timeout_seconds": timeout_seconds,
        "memory_limit_mb": memory_limit_mb,
        "max_output_bytes": max_output_bytes,
    }
    proc = subprocess.run(
        ["docker", "exec", "-i", _CONTAINER_NAME, "python3", "-c", _EXEC_SCRIPT],
        input=json.dumps(payload).encode("utf-8"),
        capture_output=True,
        timeout=timeout_seconds + 30,
    )
    assert proc.returncode == 0, f"docker exec failed: {proc.stderr.decode('utf-8', 'replace')}"
    status_line, _, body = proc.stdout.partition(b"\n")
    status_code = int(status_line)
    assert status_code == 200, f"executor returned {status_code}: {body!r}"
    return json.loads(body)


async def _execute_raw(payload: dict) -> tuple[int, dict]:
    """Like `_execute`, but returns (status_code, body) instead of
    asserting 200 — for tests that expect a non-200 response.
    """
    proc = subprocess.run(
        ["docker", "exec", "-i", _CONTAINER_NAME, "python3", "-c", _EXEC_SCRIPT],
        input=json.dumps(payload).encode("utf-8"),
        capture_output=True,
        timeout=30,
    )
    assert proc.returncode == 0, f"docker exec failed: {proc.stderr.decode('utf-8', 'replace')}"
    status_line, _, body = proc.stdout.partition(b"\n")
    return int(status_line), json.loads(body)


def _container_is_healthy() -> bool:
    health = _run(["docker", "exec", _CONTAINER_NAME, "python3", "-c", _HEALTH_CHECK_SCRIPT])
    return health.returncode == 0


def _result(body: dict) -> dict:
    assert body["status"] == "success", body
    return body["results"][0]


# ===========================================================================
# 1. Real infinite-loop timeout
# ===========================================================================


async def test_infinite_loop_is_killed_by_the_real_timeout() -> None:
    started = time.monotonic()
    body = await _execute(
        language="python", source_code="while True:\n    pass\n", timeout_seconds=4
    )
    elapsed = time.monotonic() - started
    result = _result(body)
    assert result["timed_out"] is True
    # Killed close to the requested timeout, not left running indefinitely
    # (a generous upper bound — process-group SIGKILL plus HTTP/JSON
    # round-trip overhead, not a tight timing assertion).
    assert elapsed < 15


# ===========================================================================
# 2. Real network isolation
# ===========================================================================


async def test_network_access_is_genuinely_blocked() -> None:
    code = (
        "import socket\n"
        "try:\n"
        "    s = socket.create_connection(('8.8.8.8', 53), timeout=3)\n"
        "    print('CONNECTED')\n"
        "except OSError as e:\n"
        "    print('BLOCKED:', e)\n"
    )
    body = await _execute(language="python", source_code=code, timeout_seconds=8)
    result = _result(body)
    assert "CONNECTED" not in (result["stdout"] or "")
    assert "BLOCKED" in (result["stdout"] or "") or result["exit_code"] != 0


# ===========================================================================
# 3. No application source / secrets present
# ===========================================================================


async def test_no_application_source_or_secrets_are_present() -> None:
    # `/app` legitimately exists here — it's this executor SERVICE's own
    # WORKDIR (app.py/languages.py/sandbox_runner.py, its own code, per
    # execution_worker/Dockerfile), a naming coincidence with the main
    # backend's unrelated `app/` package, not a leak. What must genuinely
    # never be present is anything from the MAIN backend (its own source
    # tree, its migrations, its pyproject) or any of the classic secret
    # env vars. Caught this distinction by actually running the test, not
    # by reasoning about the path names in the abstract.
    code = (
        "import os\n"
        "found = []\n"
        "for root in ('/app/alembic', '/app/pyproject.toml', '/app/app/core', "
        "'/backend', '/src'):\n"
        "    if os.path.exists(root):\n"
        "        found.append(root)\n"
        "print('FOUND:', found)\n"
        "print('ENV:', sorted(os.environ.keys()))\n"
    )
    body = await _execute(language="python", source_code=code)
    result = _result(body)
    stdout = result["stdout"] or ""
    assert "FOUND: []" in stdout
    # Only the minimal env this container ever receives — never a secret
    # (GEMINI_API_KEY/DATABASE_URL/JWT_SECRET_KEY etc never reach this
    # container at all per docker-compose.yml — see execution_worker/
    # sandbox_runner.py's _MINIMAL_ENV).
    for secret_name in ("GEMINI_API_KEY", "DATABASE_URL", "JWT_SECRET_KEY", "REDIS_URL"):
        assert secret_name not in stdout


# ===========================================================================
# 4. Read-only root filesystem — writes outside /tmp are blocked
# ===========================================================================


async def test_writing_outside_tmp_is_blocked_by_read_only_fs() -> None:
    code = (
        "try:\n"
        "    open('/etc/interviewiq_test_write', 'w').write('x')\n"
        "    print('WROTE')\n"
        "except OSError as e:\n"
        "    print('BLOCKED:', e)\n"
    )
    body = await _execute(language="python", source_code=code)
    result = _result(body)
    stdout = result["stdout"] or ""
    assert "WROTE" not in stdout
    assert "BLOCKED" in stdout


# ===========================================================================
# 5. No Docker socket accessible
# ===========================================================================


async def test_no_docker_socket_is_reachable() -> None:
    code = (
        "import os, socket\n"
        "path = '/var/run/docker.sock'\n"
        "if not os.path.exists(path):\n"
        "    print('NO_SOCKET_FILE')\n"
        "else:\n"
        "    try:\n"
        "        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)\n"
        "        s.connect(path)\n"
        "        print('CONNECTED_TO_DOCKER_SOCKET')\n"
        "    except OSError as e:\n"
        "        print('BLOCKED:', e)\n"
    )
    body = await _execute(language="python", source_code=code)
    result = _result(body)
    stdout = result["stdout"] or ""
    assert "CONNECTED_TO_DOCKER_SOCKET" not in stdout
    assert "NO_SOCKET_FILE" in stdout or "BLOCKED" in stdout


# ===========================================================================
# 6. Non-root execution / no privilege escalation
# ===========================================================================


async def test_process_runs_as_non_root_and_cannot_escalate() -> None:
    code = (
        "import os\n"
        "print('UID:', os.getuid())\n"
        "try:\n"
        "    os.setuid(0)\n"
        "    print('ESCALATED')\n"
        "except PermissionError as e:\n"
        "    print('BLOCKED:', e)\n"
    )
    body = await _execute(language="python", source_code=code)
    result = _result(body)
    stdout = result["stdout"] or ""
    assert "UID: 0" not in stdout
    assert "ESCALATED" not in stdout


# ===========================================================================
# 7. Memory limit enforcement
# ===========================================================================


async def test_memory_exhaustion_hits_the_real_limit_not_the_host() -> None:
    code = "x = bytearray(2 * 1024 * 1024 * 1024)\nprint('ALLOCATED')\n"
    body = await _execute(
        language="python", source_code=code, memory_limit_mb=128, timeout_seconds=8
    )
    result = _result(body)
    assert "ALLOCATED" not in (result["stdout"] or "")
    assert result["exit_code"] != 0


# ===========================================================================
# 8. Output-size limit enforcement
# ===========================================================================


async def test_output_bomb_is_capped_not_unbounded() -> None:
    code = "import sys\nfor _ in range(200000):\n    sys.stdout.write('A' * 100)\n"
    body = await _execute(
        language="python", source_code=code, max_output_bytes=4096, timeout_seconds=8
    )
    result = _result(body)
    assert result["output_truncated"] is True
    assert len(result["stdout"]) <= 4096 + 256  # small slack for the JSON/encoding boundary


# ===========================================================================
# 9. Fork-bomb / process-count limit enforcement
# ===========================================================================


async def test_fork_bomb_is_bounded_and_container_stays_healthy() -> None:
    code = (
        "import os\n"
        "spawned = 0\n"
        "try:\n"
        "    for _ in range(500):\n"
        "        os.fork()\n"
        "        spawned += 1\n"
        "except OSError as e:\n"
        "    print('BLOCKED_AFTER:', spawned, e)\n"
    )
    body = await _execute(language="python", source_code=code, timeout_seconds=8)
    result = _result(body)
    # Whatever happened, the executor itself must still be responsive —
    # RLIMIT_NPROC bounding this, not the container falling over.
    assert _container_is_healthy()
    assert result["exit_code"] is not None or result["timed_out"]


# ===========================================================================
# 10. Source code is never shell-interpreted (injection is inert)
# ===========================================================================


async def test_shell_metacharacters_in_source_are_inert() -> None:
    marker = f"interviewiq_injection_marker_{uuid.uuid4().hex}"
    code = f"print('safe output'); import os; os.system('touch /tmp/{marker}; echo done')\n"
    # The above is legitimate Python (os.system is a real call the candidate
    # COULD make) — the actual injection attempt is in how the harness
    # constructs the command around the source file, tested here by
    # embedding shell metacharacters in a string literal instead, which
    # must print literally, never be interpreted by a shell built around
    # this source text.
    injection_code = "print(\"'; rm -rf / #\")\nprint('$(whoami)')\nprint('`id`')\n"
    body = await _execute(language="python", source_code=injection_code)
    result = _result(body)
    stdout = result["stdout"] or ""
    assert "'; rm -rf / #" in stdout
    assert "$(whoami)" in stdout
    assert "`id`" in stdout
    # And the executor is still healthy — nothing broke out to a shell.
    assert _container_is_healthy()
    del code, marker  # the os.system illustration above is documentation, not asserted on


# ===========================================================================
# 11. Unsupported language rejected cleanly, nothing executed
# ===========================================================================


async def test_unsupported_language_is_rejected_without_executing() -> None:
    status_code, _ = await _execute_raw(
        {
            "language": "ruby",
            "source_code": "puts 'hi'",
            "inputs": [{"id": "t1", "stdin": ""}],
            "timeout_seconds": 5,
            "memory_limit_mb": 128,
            "max_output_bytes": 4096,
        }
    )
    assert status_code == 422


# ===========================================================================
# 12. Per-execution scratch-directory isolation between candidates
# ===========================================================================


async def test_each_execution_gets_a_fresh_cleaned_up_scratch_dir() -> None:
    marker = f"interviewiq_leftover_{uuid.uuid4().hex}"
    write_body = await _execute(
        language="python", source_code=f"open('{marker}', 'w').write('x')\nprint('WROTE')\n"
    )
    assert "WROTE" in (_result(write_body)["stdout"] or "")

    check_code = f"import os\nprint('EXISTS' if os.path.exists('{marker}') else 'ABSENT')\n"
    check_body = await _execute(language="python", source_code=check_code)
    result = _result(check_body)
    assert "ABSENT" in (result["stdout"] or "")


# ===========================================================================
# Functional correctness across all three required languages — Python,
# Java, C++ (module §6's explicit instruction, not "start with two and add
# a third later"). Not one of the 12 numbered security properties above,
# but belongs in this file for the same reason they do: it's a genuine
# claim about the real sandbox, and Python was the ONLY one of the three
# ever actually exercised end-to-end before this pair of tests existed —
# Java and C++ were both silently broken (found during a review pass, not
# by this suite, which is exactly why these two tests exist now):
#   - Java: RLIMIT_AS was too tight for the JVM's own virtual-address
#     footprint (it reserves >1GB for heap/metaspace/compressed-class-space
#     even for a trivial program) and RLIMIT_NPROC was too tight for its
#     internal GC/JIT threads — every Java submission failed compilation.
#   - C++: Docker's tmpfs mounts default to `noexec`; g++ compiled
#     successfully but the kernel refused to exec() the resulting binary
#     from /tmp — every C++ submission failed at the run step, silently,
#     with a generic-looking error.
# See languages.py's and docker-compose.yml's module docstrings for the
# full empirical account and the fix.
# ===========================================================================


async def test_java_compiles_and_runs_correctly() -> None:
    code = (
        "import java.util.Scanner;\n"
        "public class Solution {\n"
        "    public static void main(String[] args) {\n"
        "        Scanner sc = new Scanner(System.in);\n"
        "        int a = sc.nextInt();\n"
        "        System.out.println(a + 1);\n"
        "    }\n"
        "}\n"
    )
    body = await _execute(language="java", source_code=code, stdin="41", timeout_seconds=10)
    result = _result(body)
    assert result["exit_code"] == 0, result
    assert (result["stdout"] or "").strip() == "42"


async def test_cpp_compiles_and_runs_correctly() -> None:
    code = (
        "#include <bits/stdc++.h>\n"
        "using namespace std;\n"
        "int main() {\n"
        "    int a;\n"
        "    cin >> a;\n"
        "    cout << a + 1 << endl;\n"
        "    return 0;\n"
        "}\n"
    )
    body = await _execute(language="cpp", source_code=code, stdin="99", timeout_seconds=10)
    result = _result(body)
    assert result["exit_code"] == 0, result
    assert (result["stdout"] or "").strip() == "100"
