"""InterviewExecutionContext — the Module 4 -> Module 5 (LangGraph Interview
Engine) boundary (module §19).

This is the *only* thing the future Supervisor Agent needs to bootstrap
`InterviewState` (Architecture.md §5.2) for a PLANNED interview. It is
built entirely from the immutable plan (interview_sessions.plan_snapshot +
interview_rounds), never by re-querying companies/roles/templates/resumes
live — that is the whole point of the snapshot (module §9): editing a
template or uploading a newer resume after planning must never change what
Module 5 sees for an already-planned interview.

Deliberately narrow: no repository, no unrelated table, is reachable from
this module. A LangGraph agent that only ever calls
`build_execution_context(session_row)` structurally cannot reach into
companies/roles/resumes directly — exactly the boundary module §19 asks
for ("prevent LangGraph agents from directly querying many unrelated
repositories").
"""

import uuid

from pydantic import BaseModel

from app.models.enums import DifficultyLevel, InterviewMode, RoundType
from app.models.interview import InterviewSession


class RoundExecutionPlan(BaseModel):
    round_type: RoundType
    sequence_no: int
    weight: float
    planned_difficulty: DifficultyLevel
    is_required: bool


class PersonalizationContext(BaseModel):
    skills: list[str] = []
    focus_areas: list[str] = []
    missing_skills: list[str] = []
    matching_skills: list[str] = []
    project_titles: list[str] = []
    evidence_snippets: list[str] = []


class ResumeReference(BaseModel):
    """A reference, not the resume itself — Module 5 reads evidence via
    `personalization` (already extracted) or, if it needs more, via
    resume_id through Module 3's own boundary. No raw resume text/PII
    ever flows through this contract.
    """

    resume_id: uuid.UUID


class InterviewExecutionContext(BaseModel):
    interview_id: uuid.UUID
    user_id: uuid.UUID
    company_name: str | None
    role_title: str
    role_key: str | None
    mode: InterviewMode
    rounds: list[RoundExecutionPlan]
    starting_difficulty: DifficultyLevel
    personalization: PersonalizationContext | None
    resume: ResumeReference | None


def build_execution_context(session: InterviewSession) -> InterviewExecutionContext:
    """Pure — takes an InterviewSession already loaded with its `rounds`
    relationship (InterviewSessionRepository.get_owned does this). Reads
    only `plan_snapshot` + `rounds`, both immutable once the plan exists.
    """
    snapshot = session.plan_snapshot or {}
    company = snapshot.get("company")
    role = snapshot.get("role") or {}
    personalization_raw = snapshot.get("personalization")

    # is_required isn't a column on interview_rounds (only on the source
    # template_rounds) — the snapshot already captured it at plan time, so
    # it's read from there rather than re-joining template_rounds live.
    snapshot_rounds_by_seq = {r["sequence_no"]: r for r in snapshot.get("rounds", [])}
    rounds = [
        RoundExecutionPlan(
            round_type=r.round_type,
            sequence_no=r.sequence_no,
            weight=float(r.weight),
            planned_difficulty=r.planned_difficulty,
            is_required=bool(
                snapshot_rounds_by_seq.get(r.sequence_no, {}).get("is_required", True)
            ),
        )
        for r in sorted(session.rounds, key=lambda r: r.sequence_no)
    ]

    personalization = (
        PersonalizationContext(
            skills=personalization_raw.get("skills", []),
            focus_areas=personalization_raw.get("focus_areas", []),
            missing_skills=personalization_raw.get("missing_skills", []),
            matching_skills=personalization_raw.get("matching_skills", []),
            project_titles=personalization_raw.get("project_titles", []),
            evidence_snippets=personalization_raw.get("evidence_snippets", []),
        )
        if personalization_raw
        else None
    )

    return InterviewExecutionContext(
        interview_id=session.id,
        user_id=session.user_id,
        company_name=company["name"] if company else None,
        role_title=role.get("title", ""),
        role_key=role.get("role_key"),
        mode=session.mode,
        rounds=rounds,
        starting_difficulty=session.starting_difficulty,
        personalization=personalization,
        resume=ResumeReference(resume_id=session.resume_id) if session.resume_id else None,
    )
