"""The actual isolation mechanics — module §5. This file is the whole
reason the `executor` container exists: it never runs anything the
candidate's process couldn't have run on its own (no docker calls, no
socket), it just does it under real OS-enforced limits, in a scratch
directory that's always cleaned up, and reports back exactly what
happened.

Layered isolation actually implemented here (documented precisely, not
overclaimed — see backend/README.md's Module 6 section for the honest
account of what this does and doesn't guarantee):
  - non-root execution: the whole container runs as a non-root user
    (execution_worker/Dockerfile) — nothing here elevates privilege.
  - no application env vars / no secrets: subprocesses get an explicit,
    minimal env dict, never os.environ or anything inherited from a
    parent that might carry secrets (this container never receives any
    in the first place — see docker-compose.yml — but this is defense in
    depth, not the only reason it's safe).
  - CPU limit: RLIMIT_CPU.
  - memory limit: RLIMIT_AS (virtual address space) — `_with_language_overrides`
    raises this for languages whose own toolchain needs more headroom than a
    typical candidate program (the JVM reserves >1GB of virtual address
    space just for its own internal bookkeeping; see languages.py's module
    docstring for the empirical findings), on top of an actual heap cap
    (`-Xmx`) passed directly to the toolchain, which is what really bounds
    memory for those languages now that RLIMIT_AS itself has to be loose.
  - process-count limit: RLIMIT_NPROC — a real but *shared-uid* limit
    (documented caveat: this container runs one uid for both the FastAPI
    server and every sandboxed subprocess, so this is fork-bomb
    mitigation, not a hard per-execution guarantee — see the module
    docstring in app.py) — also raised per-language where the toolchain
    itself needs more (g++ forking `cc1plus`, the JVM's internal threads).
  - output-size limit: RLIMIT_FSIZE on the redirected stdout/stderr files
    — kernel-enforced, not "read everything then truncate" (which would
    let an output bomb exhaust this container's own memory first).
  - wall-clock timeout: subprocess.communicate(timeout=...), whole
    process GROUP killed via os.killpg on breach (a forked grandchild
    would otherwise survive `proc.kill()` alone).
  - cleanup: every execution's scratch directory lives under a
    tempfile.TemporaryDirectory() context manager — deleted on every exit
    path (success, compile failure, runtime crash, timeout, output-limit
    kill, or an unexpected exception), never left behind.

NOT implemented (documented limitation, not hidden — module §5's "do not
claim production-grade isolation unless genuinely supported"): this is
process isolation *within* one locked-down, network-isolated, read-only-
root-filesystem container — not a fresh container (or VM) per execution.
Concurrent submissions share this container's kernel/process table.
Network isolation itself is NOT done here at all — it's enforced one
layer up, by docker-compose.yml putting this whole container on an
`internal: true` network with no route to the internet or host, which is
a stronger, unbypassable guarantee than anything a subprocess-level flag
could add.
"""

import os
import signal
import subprocess
import time
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

from languages import LanguageConfig

# Compilation is a one-time, fixed cost regardless of test-case count —
# generous but bounded so a pathological compile (e.g. template-heavy C++)
# can't hang the container indefinitely. 30s (Module 6 final-review fix,
# raised from 20s): measured directly, not assumed — a completely ordinary
# `#include <bits/stdc++.h>` (a common, legitimate competitive-programming
# idiom, not a pathological case) took ~11.4s to compile uncontended under
# this container's real rlimits/cgroup caps, which left too little margin
# once real concurrent load (multiple candidates compiling C++ at once,
# sharing this container's `cpus: 2.0` quota) is accounted for — confirmed
# by reproducing a live "Compilation timed out." failure under concurrent
# load at the old 20s budget. 30s keeps a genuine ceiling (still far below
# what a real infinite-template-recursion attack would need to get caught)
# while giving legitimate slow-but-normal compiles real headroom.
_COMPILE_TIMEOUT_SECONDS = 30
_MINIMAL_ENV = {"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": "/tmp", "LANG": "C.UTF-8"}


@dataclass
class ExecutionLimits:
    timeout_seconds: int
    memory_limit_mb: int
    max_output_bytes: int
    max_processes: int = 32


@dataclass
class ProcessOutcome:
    stdout: str
    stderr: str
    exit_code: int | None
    runtime_ms: int
    timed_out: bool
    output_truncated: bool


@dataclass
class CompileOutcome:
    success: bool
    message: str = ""
    runtime_ms: int = 0


def _preexec(limits: ExecutionLimits):
    """Runs in the child, after fork(), before exec() — every rlimit set
    here is inherited across exec into whatever actually runs (the
    compiler, or the candidate's own program). New session/process group
    so a timeout kill can reap the whole tree, not just the direct child.
    """

    def _apply() -> None:
        os.setsid()
        cpu = limits.timeout_seconds + 2
        resource_module.setrlimit(resource_module.RLIMIT_CPU, (cpu, cpu))
        mem_bytes = limits.memory_limit_mb * 1024 * 1024
        resource_module.setrlimit(resource_module.RLIMIT_AS, (mem_bytes, mem_bytes))
        resource_module.setrlimit(
            resource_module.RLIMIT_NPROC, (limits.max_processes, limits.max_processes)
        )
        resource_module.setrlimit(
            resource_module.RLIMIT_FSIZE, (limits.max_output_bytes, limits.max_output_bytes)
        )

    return _apply


try:
    import resource as resource_module
except ImportError:  # pragma: no cover — resource is POSIX-only; this
    # service only ever runs in the Linux container, never imported by the
    # main backend on Windows, but guarded so a stray import doesn't crash
    # tooling that scans this file on a non-POSIX host.
    resource_module = None  # type: ignore[assignment]


def _run_process(
    cmd: list[str], *, cwd: Path, stdin_text: str, limits: ExecutionLimits
) -> ProcessOutcome:
    stdout_path = cwd / "_stdout.txt"
    stderr_path = cwd / "_stderr.txt"
    started = time.monotonic()
    timed_out = False
    exit_code: int | None = None

    with open(stdout_path, "wb") as out_f, open(stderr_path, "wb") as err_f:
        proc = subprocess.Popen(
            cmd,
            cwd=cwd,
            stdin=subprocess.PIPE,
            stdout=out_f,
            stderr=err_f,
            preexec_fn=_preexec(limits),
            env=_MINIMAL_ENV,
        )
        try:
            proc.communicate(
                input=stdin_text.encode("utf-8", errors="replace"), timeout=limits.timeout_seconds
            )
            exit_code = proc.returncode
        except subprocess.TimeoutExpired:
            timed_out = True
            with suppress(ProcessLookupError):
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            with suppress(subprocess.TimeoutExpired):
                proc.wait(timeout=2)  # already SIGKILLed; best-effort reap only

    runtime_ms = int((time.monotonic() - started) * 1000)
    raw_stdout = stdout_path.read_bytes()
    raw_stderr = stderr_path.read_bytes()
    # `>=`, not `>` — RLIMIT_FSIZE makes the file physically incapable of
    # exceeding max_output_bytes, so a strict `>` here can never fire
    # (confirmed by actually hitting this limit, not by reasoning about it:
    # the kernel returns EFBIG on the write() call once the file reaches
    # exactly the limit, which for buffered stdio surfaces as an uncaught
    # `OSError: [Errno 27] File too large` — a normal Python exit code 1,
    # not a raw SIGXFSZ-terminated process, so exit_code alone doesn't
    # reveal it either). A file sized exactly at the limit is the real,
    # practical signal that output was cut off — a legitimate program's
    # output landing on that exact byte boundary is not a realistic
    # candidate-code scenario.
    output_truncated = (
        len(raw_stdout) >= limits.max_output_bytes or len(raw_stderr) >= limits.max_output_bytes
    )
    return ProcessOutcome(
        stdout=raw_stdout[: limits.max_output_bytes].decode("utf-8", errors="replace"),
        stderr=raw_stderr[: limits.max_output_bytes].decode("utf-8", errors="replace"),
        exit_code=exit_code,
        runtime_ms=runtime_ms,
        timed_out=timed_out,
        output_truncated=output_truncated,
    )


def _with_language_overrides(language: LanguageConfig, limits: ExecutionLimits) -> ExecutionLimits:
    """Some toolchains (the JVM, g++'s subprocess spawning) need more
    RLIMIT_AS/RLIMIT_NPROC headroom than a typical candidate program does,
    independent of the requested memory_limit_mb — see languages.py's
    module docstring for the empirical findings behind these numbers.
    `min_*` fields default to 0, a no-op for every language that doesn't
    need this (identical behavior to before this override existed).
    """
    if not language.min_address_space_mb and not language.min_process_limit:
        return limits
    return ExecutionLimits(
        timeout_seconds=limits.timeout_seconds,
        memory_limit_mb=max(limits.memory_limit_mb, language.min_address_space_mb),
        max_output_bytes=limits.max_output_bytes,
        max_processes=max(limits.max_processes, language.min_process_limit),
    )


def compile_if_needed(language: LanguageConfig, *, cwd: Path) -> CompileOutcome:
    if language.compile_cmd is None:
        return CompileOutcome(success=True)
    limits = _with_language_overrides(
        language,
        ExecutionLimits(
            timeout_seconds=_COMPILE_TIMEOUT_SECONDS, memory_limit_mb=512, max_output_bytes=65536
        ),
    )
    outcome = _run_process(language.compile_cmd, cwd=cwd, stdin_text="", limits=limits)
    if outcome.timed_out:
        return CompileOutcome(
            success=False, message="Compilation timed out.", runtime_ms=outcome.runtime_ms
        )
    if outcome.exit_code != 0:
        return CompileOutcome(
            success=False,
            message=outcome.stderr or "Compilation failed.",
            runtime_ms=outcome.runtime_ms,
        )
    return CompileOutcome(success=True, runtime_ms=outcome.runtime_ms)


def run_against_input(
    language: LanguageConfig, *, cwd: Path, stdin_text: str, limits: ExecutionLimits
) -> ProcessOutcome:
    effective_limits = _with_language_overrides(language, limits)
    return _run_process(language.run_cmd, cwd=cwd, stdin_text=stdin_text, limits=effective_limits)
