"""CodeExecutor abstraction — Architecture.md §6.

The Evaluation Agent and coding-round services depend only on this
Protocol. Swapping DockerSandboxExecutor for Judge0Executor later is a
config change (CODE_EXECUTION_BACKEND), not a refactor.
"""

from dataclasses import dataclass, field
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
    # Structured signals (not string-parsed from `stderr`) — module §7
    # needs a real CodeExecutionStatus per submission, derived
    # deterministically from these, not guessed from message text. Default
    # values keep every pre-existing FakeCodeExecutor call site valid.
    timed_out: bool = False
    exit_code: int | None = None
    output_truncated: bool = False


@dataclass(frozen=True, slots=True)
class ExecutionOutcome:
    """The result of running one submission against a set of test cases.
    Compilation is a property of the *submission*, not of any individual
    test case — modeled once here rather than duplicated onto every
    TestCaseResult (which would force callers to infer a whole-submission
    fact by inspecting per-test stderr text, module §7's "structured
    status", not string matching).
    """

    compiled: bool
    compile_message: str | None
    results: list[TestCaseResult] = field(default_factory=list)


class CodeExecutor(Protocol):
    async def run(
        self, *, source_code: str, language: str, test_cases: list[TestCase]
    ) -> ExecutionOutcome:
        """Execute `source_code` against every test case. If compilation
        fails, `results` is empty and `compiled=False` — no test case ever
        ran. Otherwise `compiled=True` and `results` has exactly one
        TestCaseResult per test case, in the same order.
        """
        ...
