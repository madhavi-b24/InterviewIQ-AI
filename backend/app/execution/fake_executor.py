"""FakeCodeExecutor — deterministic, no subprocess/container/network call.
Mirrors every other fake provider in this codebase (constructor flags,
`.reset()`, `.calls` log, module-level singleton + getter — see
app/services/interview_intelligence/fake_provider.py for the template this
follows).

Since there's no way to "fake run" arbitrary source code deterministically,
tests communicate intent via magic substrings in `source_code` rather than
writing real programs — reads clearly at the call site
(`source_code="# CORRECT_SOLUTION"`) and needs no actual Python/Java/C++
toolchain to run the test suite that doesn't specifically target the real
sandbox (see tests/test_sandbox_security.py for the tests that do,
against the real `executor` container).
"""

from app.execution.base import CodeExecutor, ExecutionOutcome, TestCase, TestCaseResult
from app.execution.exceptions import CodeExecutionProviderError, CodeExecutionTimeoutError

_MARKER_COMPILE_ERROR = "COMPILE_ERROR"
_MARKER_RUNTIME_ERROR = "RUNTIME_ERROR"
_MARKER_TIME_LIMIT = "TIME_LIMIT"
_MARKER_OUTPUT_LIMIT = "OUTPUT_LIMIT"
_MARKER_INCORRECT = "INCORRECT_SOLUTION"


class FakeCodeExecutor(CodeExecutor):
    def __init__(self, *, fail: bool = False, timeout: bool = False) -> None:
        self.fail = fail
        self.timeout = timeout
        self.calls: list[str] = []

    def reset(self) -> None:
        self.fail = False
        self.timeout = False
        self.calls = []

    async def run(
        self, *, source_code: str, language: str, test_cases: list[TestCase]
    ) -> ExecutionOutcome:
        self.calls.append("run")
        if self.timeout:
            raise CodeExecutionTimeoutError("fake executor: simulated timeout")
        if self.fail:
            raise CodeExecutionProviderError("fake executor: simulated provider failure")

        if _MARKER_COMPILE_ERROR in source_code:
            return ExecutionOutcome(
                compiled=False,
                compile_message="Fake compile error: syntax error on line 1",
                results=[],
            )

        results: list[TestCaseResult] = []
        for tc in test_cases:
            if _MARKER_RUNTIME_ERROR in source_code:
                results.append(
                    TestCaseResult(
                        test_case_id=tc.id,
                        passed=False,
                        actual_output=None,
                        runtime_ms=8,
                        memory_kb=4096,
                        stderr="Fake runtime error: division by zero",
                        exit_code=1,
                    )
                )
            elif _MARKER_TIME_LIMIT in source_code:
                results.append(
                    TestCaseResult(
                        test_case_id=tc.id,
                        passed=False,
                        actual_output=None,
                        runtime_ms=10_000,
                        memory_kb=None,
                        stderr="Time limit exceeded (10s).",
                        timed_out=True,
                        exit_code=None,
                    )
                )
            elif _MARKER_OUTPUT_LIMIT in source_code:
                results.append(
                    TestCaseResult(
                        test_case_id=tc.id,
                        passed=False,
                        actual_output="[fake] truncated output...",
                        runtime_ms=5,
                        memory_kb=4096,
                        stderr="[output truncated at the size limit]",
                        exit_code=0,
                        output_truncated=True,
                    )
                )
            elif _MARKER_INCORRECT in source_code:
                results.append(
                    TestCaseResult(
                        test_case_id=tc.id,
                        passed=False,
                        actual_output="[fake] deliberately wrong output",
                        runtime_ms=6,
                        memory_kb=4096,
                        stderr=None,
                        exit_code=0,
                    )
                )
            else:
                # Default / explicit "CORRECT_SOLUTION" marker — echoes the
                # test case's own expected_output back, so a genuinely
                # correct fake solution always passes every case it's
                # given regardless of what the catalog's test data is.
                results.append(
                    TestCaseResult(
                        test_case_id=tc.id,
                        passed=True,
                        actual_output=tc.expected_output,
                        runtime_ms=6,
                        memory_kb=4096,
                        stderr=None,
                        exit_code=0,
                    )
                )
        return ExecutionOutcome(compiled=True, compile_message=None, results=results)


_singleton = FakeCodeExecutor()


def get_fake_code_executor() -> FakeCodeExecutor:
    return _singleton
