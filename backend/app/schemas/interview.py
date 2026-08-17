"""Request/response DTOs for interview planning (API.md §4, Module 4).

`POST /interview-sessions` extends API.md's originally-documented body
(`{ resume_id, company_id?, role_id, template_id, difficulty_override? }`)
rather than replacing it — adds `mode` (optional, validated against the
template's own mode when given) and renames `difficulty_override` to
`difficulty` with an explicit `"auto"` option (module §7). Deviation
documented here the same way GapAnalysisRequest documents its own
deviation in app/schemas/resume.py.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.models.enums import (
    DifficultyLevel,
    InterviewMode,
    RequestedDifficulty,
    RoundType,
    SessionStatus,
)


class InterviewPlanRequest(BaseModel):
    company_id: uuid.UUID | None = None
    role_id: uuid.UUID
    template_id: uuid.UUID
    mode: InterviewMode | None = None
    difficulty: RequestedDifficulty = RequestedDifficulty.AUTO
    resume_id: uuid.UUID | None = None


class RoundPlanOut(BaseModel):
    round_type: RoundType
    sequence_no: int
    weight: Decimal
    planned_difficulty: DifficultyLevel
    is_required: bool


class DifficultyPlanOut(BaseModel):
    requested: RequestedDifficulty
    starting: DifficultyLevel
    reasons: list[str]


class PersonalizationOut(BaseModel):
    """Deliberately narrow — evidence-grounded signals only, never raw
    resume text or contact info (module §9, §10). Mirrors
    app/services/resume/interview_context.py's shape.
    """

    resume_id: uuid.UUID
    skills: list[str]
    focus_areas: list[str]
    missing_skills: list[str]
    matching_skills: list[str]
    project_titles: list[str]
    evidence_snippets: list[str]


class InterviewSessionSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: SessionStatus
    company_id: uuid.UUID | None
    role_id: uuid.UUID
    template_id: uuid.UUID
    mode: InterviewMode
    current_difficulty: DifficultyLevel
    starting_difficulty: DifficultyLevel
    requested_difficulty: RequestedDifficulty
    resume_id: uuid.UUID | None
    created_at: datetime


class InterviewSessionDetail(InterviewSessionSummary):
    current_round_sequence: int
    started_at: datetime | None
    completed_at: datetime | None


class InterviewPlanResponse(BaseModel):
    """GET /interview-sessions/{id}/plan — the full immutable snapshot."""

    interview_id: uuid.UUID
    status: SessionStatus
    # None for a company-agnostic plan (module §8) — plan_snapshot["company"]
    # is None whenever InterviewSession.company_id is None.
    company: dict | None
    role: dict
    template: dict
    mode: InterviewMode
    rounds: list[RoundPlanOut]
    difficulty: DifficultyPlanOut
    personalization: PersonalizationOut | None
    created_at: datetime
