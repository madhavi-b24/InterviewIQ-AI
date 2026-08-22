"""Request/response DTOs for the coding round (Module 6). Kept separate
from schemas/interview_turn.py — a different REST sub-resource lifecycle
(Run/Submit are polled, multi-attempt; a text answer is one synchronous
call) — same reasoning interview_turn.py's own docstring gives for being
split from schemas/interview.py.

**Hidden tests never leave this module's boundary** (module §8): every
`*Out` schema below that can be reached by a candidate excludes hidden
test cases' input/expected_output entirely. `CodeSubmissionOut.test_results`
only ever contains entries for the SAMPLE test cases in that submission's
own results — hidden test outcomes are folded into the aggregate
`passed_test_count`/`total_test_count` only, never itemized. A Run only
ever executes sample test cases in the first place (module §6); a Submit
executes all of them, but only the sample subset is itemized here.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import CodeExecutionStatus, DifficultyLevel


class CodingSampleTestCaseOut(BaseModel):
    input: str
    expected_output: str


class CodingProblemOut(BaseModel):
    """GET .../coding-problem — the candidate-facing view of the current
    coding Question. Built from Question.coding_snapshot (module §8's
    catalog-is-mutable-but-the-asked-question-is-immutable rule) plus the
    live QuestionTestCase rows filtered to is_sample=True only.
    """

    question_id: uuid.UUID
    title: str
    description: str
    difficulty: DifficultyLevel
    topics: list[str]
    constraints: str | None
    expected_time_complexity: str | None
    expected_space_complexity: str | None
    supported_languages: list[str]
    starter_code: dict[str, str]
    sample_test_cases: list[CodingSampleTestCaseOut]


class CodeSubmissionRequest(BaseModel):
    language: str
    source_code: str = Field(min_length=1, max_length=100_000)
    is_final: bool = False


class CodeSubmissionTestResultOut(BaseModel):
    """Sample test cases only — see module docstring."""

    input: str
    expected_output: str
    actual_output: str | None
    passed: bool
    runtime_ms: int | None
    stderr: str | None


class CodeSubmissionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    question_id: uuid.UUID
    attempt_no: int
    is_final: bool
    language: str
    execution_status: CodeExecutionStatus
    passed_test_count: int | None
    total_test_count: int | None
    total_runtime_ms: int | None
    # Populated only for COMPILE_ERROR (the compiler's own message) or a
    # genuine sandbox/provider infra failure (module §7) — never for a
    # normal wrong-answer/runtime-error outcome, where per-test stderr in
    # sample_test_results already carries the relevant detail.
    error_message: str | None = None
    sample_test_results: list[CodeSubmissionTestResultOut] = Field(default_factory=list)
    created_at: datetime
    graded_at: datetime | None


class CodingEvaluationOut(BaseModel):
    correctness_score: float
    correctness_explanation: str
    readability_score: float
    readability_explanation: str
    optimization_score: float
    optimization_explanation: str
    edge_case_score: float
    edge_case_explanation: str
    time_complexity: str | None
    space_complexity: str | None
    overall_code_score: float
    strengths: list[str]
    weaknesses: list[str]
    recommendations: list[str]
