"""Request/response DTOs for interview EXECUTION (API.md §4's
start/current-turn/answers/abandon rows, Module 5). Kept separate from
schemas/interview.py, which stays scoped to planning (its own docstring
already says so) — these are a different REST sub-resource lifecycle.

API.md sketches the route table and one example `/answers` response shape
but not the exact request bodies — same situation Module 4 was in for
`POST /interview-sessions`, resolved the same way: design the shape,
document the deviation here rather than silently diverging.

**Deviation from API.md's sketch**: `POST /answers`' body is
`{question_id, answer_text}` — requiring `question_id` explicitly (rather
than implicitly "the current question") makes the idempotency/staleness
check in InterviewExecutionService unambiguous: a request naming a
question that isn't the session's current pending one is a clean,
diagnosable `409 STALE_QUESTION_ID`, not a guess. `difficulty_signal` in
the response is nested under `evaluation.difficulty_signal` rather than a
top-level key, to keep every dimension (technical/problem_solving/
communication/confidence) and the signal that came from them together.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import DifficultyLevel, DifficultySignal, RoundType, SessionStatus


class AnswerSubmitRequest(BaseModel):
    question_id: uuid.UUID
    answer_text: str


class ScoreOut(BaseModel):
    """Every score paired with its explanation — never a bare number,
    matching this project's schema-wide convention (Database.md §0).
    """

    score: float
    explanation: str


class EvaluationOut(BaseModel):
    technical: ScoreOut
    problem_solving: ScoreOut
    communication: ScoreOut
    confidence: ScoreOut
    difficulty_signal: DifficultySignal


class QuestionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    question_text: str
    topic: str
    difficulty: DifficultyLevel
    round_type: RoundType
    parent_question_id: uuid.UUID | None


class NextOut(BaseModel):
    """Mirrors API.md's documented `/answers` response shape: `type` is
    one of "question" / "round_complete" / "session_complete";
    `question`/`round_complete` fields are populated accordingly.
    """

    type: str
    question: QuestionOut | None = None
    round_type: RoundType | None = None  # populated when type == "round_complete"


class StartInterviewOut(BaseModel):
    interview_id: uuid.UUID
    status: SessionStatus
    current_round: RoundType
    current_difficulty: DifficultyLevel
    question: QuestionOut


class AnswerResponseOut(BaseModel):
    interview_id: uuid.UUID
    status: SessionStatus
    evaluation: EvaluationOut
    previous_difficulty: DifficultyLevel
    current_difficulty: DifficultyLevel
    next: NextOut


class CurrentTurnOut(BaseModel):
    """GET /interview-sessions/{id}/current-turn — pure read, no graph
    invocation, no side effects (module §6's "lets a candidate come back
    later" requirement)."""

    interview_id: uuid.UUID
    status: SessionStatus
    current_round: RoundType | None
    current_difficulty: DifficultyLevel
    question: QuestionOut | None
    interview_complete: bool


class AbandonOut(BaseModel):
    interview_id: uuid.UUID
    status: SessionStatus
    completed_at: datetime | None
