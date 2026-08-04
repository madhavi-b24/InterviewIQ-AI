"""CodeExecutor abstraction — Architecture.md §6.

The Evaluation Agent and coding-round services depend only on this
Protocol. Swapping DockerSandboxExecutor for Judge0Executor later is a
config change (CODE_EXECUTION_BACKEND), not a refactor.
"""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class TestCase:
    id: str
    input: str
    expected_output: str
    is_sample: bool
    weight: float


@dataclass(frozen=True, slots=True)
class TestCaseResult:
    test_case_id: str
    passed: bool
    actual_output: str | None
    runtime_ms: int | None
    memory_kb: int | None
    stderr: str | None


class CodeExecutor(Protocol):
    async def run(
        self, *, source_code: str, language: str, test_cases: list[TestCase]
    ) -> list[TestCaseResult]:
        """Execute `source_code` against every test case and return one
        TestCaseResult per test case, in the same order.
        """
        ...
