"""The sandbox executor's own tiny HTTP service — module §4/§12: this is
the ONLY thing `backend`'s DockerSandboxExecutor talks to; nothing here
imports the main `app/` package, nothing here has a Docker socket, no
project source beyond this directory is present in the image, and this
container receives zero application secrets (see docker-compose.yml — no
`env_file`, no `GEMINI_API_KEY`/`DATABASE_URL`/etc are ever passed to it).

Deliberately does NOT know about "expected output"/pass-fail — it runs
code against stdin and reports back exactly what happened (stdout,
stderr, exit code, timing, whether it timed out or got truncated). The
actual-vs-expected comparison happens in the trusted backend
(app/execution/docker_sandbox.py), keeping this service a pure "run this,
tell me what happened" primitive — it never needs to see a hidden test's
expected answer at all.
"""

import asyncio
import tempfile
from pathlib import Path

from fastapi import FastAPI, HTTPException
from languages import get_language_config, is_supported
from pydantic import BaseModel, Field
from sandbox_runner import ExecutionLimits, compile_if_needed, run_against_input

app = FastAPI(title="InterviewIQ Sandbox Executor")


class TestInput(BaseModel):
    id: str
    stdin: str = ""


class ExecuteRequest(BaseModel):
    language: str
    source_code: str
    inputs: list[TestInput] = Field(default_factory=list)
    timeout_seconds: int = 10
    memory_limit_mb: int = 256
    max_output_bytes: int = 65536


class TestOutcome(BaseModel):
    id: str
    stdout: str
    stderr: str
    exit_code: int | None
    runtime_ms: int
    timed_out: bool
    output_truncated: bool


class ExecuteResponse(BaseModel):
    # "success" | "compile_error" | "unsupported_language"
    status: str
    compile_message: str | None = None
    results: list[TestOutcome] = Field(default_factory=list)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/execute")
async def execute(request: ExecuteRequest) -> ExecuteResponse:
    if not is_supported(request.language):
        raise HTTPException(status_code=422, detail=f"unsupported language: {request.language!r}")
    language = get_language_config(request.language)

    # Hard caps regardless of what the caller asked for — this service is
    # only ever called by the trusted backend, but it still never trusts a
    # request to set its own limits arbitrarily high.
    timeout_seconds = min(request.timeout_seconds, 30)
    memory_limit_mb = min(request.memory_limit_mb, 512)
    max_output_bytes = min(request.max_output_bytes, 1_048_576)  # 1 MiB hard ceiling

    # Every execution gets its own fresh scratch directory, deleted on
    # every exit path (success, compile failure, exception) via the
    # context manager — module §17.
    with tempfile.TemporaryDirectory(prefix="sandbox-") as tmpdir:
        cwd = Path(tmpdir)
        (cwd / language.source_filename).write_text(request.source_code, encoding="utf-8")

        compile_outcome = await asyncio.to_thread(compile_if_needed, language, cwd=cwd)
        if not compile_outcome.success:
            return ExecuteResponse(status="compile_error", compile_message=compile_outcome.message)

        limits = ExecutionLimits(
            timeout_seconds=timeout_seconds,
            memory_limit_mb=memory_limit_mb,
            max_output_bytes=max_output_bytes,
        )
        results: list[TestOutcome] = []
        for test_input in request.inputs:
            outcome = await asyncio.to_thread(
                run_against_input,
                language,
                cwd=cwd,
                stdin_text=test_input.stdin,
                limits=limits,
            )
            results.append(
                TestOutcome(
                    id=test_input.id,
                    stdout=outcome.stdout,
                    stderr=outcome.stderr,
                    exit_code=outcome.exit_code,
                    runtime_ms=outcome.runtime_ms,
                    timed_out=outcome.timed_out,
                    output_truncated=outcome.output_truncated,
                )
            )
        return ExecuteResponse(status="success", results=results)
