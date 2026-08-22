"""DockerSandboxExecutor — the real CodeExecutor implementation (Module 6).

Despite the name (kept for continuity with the existing
CODE_EXECUTION_BACKEND="docker_sandbox" config value and the pre-existing
class name nothing else needed to change), this never touches the Docker
API or a socket directly. It makes a plain HTTP call (httpx, already a
project dependency) to a dedicated sibling container
(`backend/execution_worker/`) that does the actual sandboxed execution —
see docs/Architecture.md §6 and that package's own docstrings for exactly
what isolation it provides and doesn't.

Comparison logic lives HERE, not in the executor service: the executor is
asked to run code against raw stdin and report back what happened — it is
never told what the "expected" output is, so it never needs to see a
hidden test case's answer. This module owns comparing
`actual_output`/`expected_output` (normalized: trailing whitespace
stripped, matching how virtually every real judge compares output) to
produce `TestCaseResult.passed`, and owns turning the executor's raw,
untyped JSON into the typed `timed_out`/`exit_code`/`output_truncated`
signals CodingRoundService uses to derive a structured CodeExecutionStatus
(module §7) — never by string-matching `stderr`.
"""

import httpx

from app.core.config import Settings
from app.core.logging import get_logger
from app.execution.base import CodeExecutor, ExecutionOutcome, TestCase, TestCaseResult
from app.execution.exceptions import CodeExecutionProviderError, CodeExecutionTimeoutError

logger = get_logger(__name__)


def _normalize(text: str) -> str:
    return text.strip()


class DockerSandboxExecutor(CodeExecutor):
    def __init__(self, settings: Settings) -> None:
        self._base_url = settings.EXECUTOR_BASE_URL
        self._timeout_seconds = settings.CODE_EXECUTION_TIMEOUT_SECONDS
        self._memory_limit_mb = settings.CODE_EXECUTION_MEMORY_LIMIT_MB
        self._max_output_bytes = settings.CODE_EXECUTION_MAX_OUTPUT_BYTES

    async def run(
        self, *, source_code: str, language: str, test_cases: list[TestCase]
    ) -> ExecutionOutcome:
        # Deliberately never sends expected_output to the executor — see
        # module docstring. Only id + input (as stdin) cross that boundary.
        payload = {
            "language": language,
            "source_code": source_code,
            "inputs": [{"id": tc.id, "stdin": tc.input} for tc in test_cases],
            "timeout_seconds": self._timeout_seconds,
            "memory_limit_mb": self._memory_limit_mb,
            "max_output_bytes": self._max_output_bytes,
        }
        logger.info(
            "code_execution.run.started",
            language=language,
            source_chars=len(source_code),
            test_case_count=len(test_cases),
        )
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout_seconds * max(len(test_cases), 1) + 30
            ) as client:
                response = await client.post(f"{self._base_url}/execute", json=payload)
        except httpx.TimeoutException as exc:
            raise CodeExecutionTimeoutError(
                "sandbox executor did not respond within the expected window"
            ) from exc
        except httpx.HTTPError as exc:
            raise CodeExecutionProviderError(f"sandbox executor unreachable: {exc}") from exc

        if response.status_code == 422:
            raise CodeExecutionProviderError(
                f"sandbox executor rejected the request: {response.text}"
            )
        if response.status_code != 200:
            raise CodeExecutionProviderError(
                f"sandbox executor returned unexpected status {response.status_code}"
            )

        try:
            body = response.json()
        except ValueError as exc:
            raise CodeExecutionProviderError(
                "sandbox executor returned a non-JSON response"
            ) from exc

        if body.get("status") == "compile_error":
            logger.info("code_execution.run.compile_error", language=language)
            message = body.get("compile_message") or "Compilation failed."
            return ExecutionOutcome(compiled=False, compile_message=message, results=[])

        results_by_id = {r["id"]: r for r in body.get("results", [])}
        test_case_results: list[TestCaseResult] = []
        for tc in test_cases:
            raw = results_by_id.get(tc.id)
            if raw is None:
                # Should not happen — the executor returns one result per
                # input it was given — but never trust that blindly.
                test_case_results.append(
                    TestCaseResult(
                        test_case_id=tc.id,
                        passed=False,
                        actual_output=None,
                        runtime_ms=None,
                        memory_kb=None,
                        stderr="No result returned for this test case.",
                        exit_code=None,
                    )
                )
                continue

            actual = raw.get("stdout", "")
            timed_out = bool(raw.get("timed_out"))
            exit_code = raw.get("exit_code")
            output_truncated = bool(raw.get("output_truncated"))
            passed = (
                not timed_out
                and exit_code == 0
                and _normalize(actual) == _normalize(tc.expected_output)
            )
            stderr = raw.get("stderr") or None
            if timed_out:
                stderr = f"Time limit exceeded ({self._timeout_seconds}s)."
            elif output_truncated:
                stderr = (stderr or "") + " [output truncated at the size limit]"

            test_case_results.append(
                TestCaseResult(
                    test_case_id=tc.id,
                    passed=passed,
                    actual_output=actual,
                    runtime_ms=raw.get("runtime_ms"),
                    memory_kb=None,  # not measured by this MVP executor — see Known limitations
                    stderr=stderr,
                    timed_out=timed_out,
                    exit_code=exit_code,
                    output_truncated=output_truncated,
                )
            )

        logger.info(
            "code_execution.run.completed",
            language=language,
            passed_count=sum(1 for r in test_case_results if r.passed),
            total_count=len(test_case_results),
        )
        return ExecutionOutcome(compiled=True, compile_message=None, results=test_case_results)
