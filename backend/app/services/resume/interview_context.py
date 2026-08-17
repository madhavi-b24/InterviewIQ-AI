"""Interview Engine integration boundary (module §13).

The Interview Engine itself is explicitly out of scope for this module —
this is only the read-only seam a future Question Generator / Difficulty
Agent will call to pull a candidate's active resume context. No new
public API endpoint: this is a service-layer function, called in-process
by whatever future module needs it (Architecture.md's Service layer can
call another domain's service directly; only the API layer is restricted
to "one service call per route").

Deliberately returns a flat, LLM-prompt-friendly shape rather than the
ORM graph — the whole point is to hand a Question Generator agent
something it can drop straight into a prompt, evidence snippets included.
"""

import uuid

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import DifficultyLevel
from app.models.resume import Resume
from app.repositories.resume import ResumeRepository


class ProjectContext(BaseModel):
    title: str
    description: str | None
    technologies: list[str]
    evidence: str | None


class ExperienceContext(BaseModel):
    company: str
    title: str
    technologies: list[str]
    evidence: str | None


class RoleReadinessContext(BaseModel):
    role_key: str
    matching_skills: list[str]
    missing_skills: list[str]
    recommended_difficulty: DifficultyLevel


class ResumeInterviewContext(BaseModel):
    """What the future Interview Engine gets for one candidate: enough to
    ground question selection and difficulty in what the candidate
    actually claimed, without re-deriving it from raw resume text.
    """

    resume_id: uuid.UUID
    candidate_name: str | None
    professional_summary: str | None
    skills: list[str]
    projects: list[ProjectContext]
    experience: list[ExperienceContext]
    role_readiness: RoleReadinessContext | None
    recommended_difficulty: DifficultyLevel | None
    evidence_snippets: list[str]


def build_resume_interview_context(resume: Resume) -> ResumeInterviewContext:
    """Pure transform: an already-loaded Resume (with its children eagerly
    loaded — skills/projects/experience/gap_analysis) to the flat context
    shape. Extracted from get_active_resume_context (module §13) so Module 4
    (app/services/planning/interview_planner.py) can build the same
    personalization context for an *explicitly selected*, not-necessarily-
    active resume, without duplicating this assembly logic.
    """
    skills = [skill.skill_name for skill in resume.skills]
    projects = [
        ProjectContext(
            title=p.title,
            description=p.description,
            technologies=p.technologies,
            evidence=p.evidence_text,
        )
        for p in resume.projects
    ]
    experience = [
        ExperienceContext(
            company=e.company, title=e.title, technologies=e.technologies, evidence=e.evidence_text
        )
        for e in resume.experience
    ]

    gap = resume.gap_analysis
    role_readiness = (
        RoleReadinessContext(
            role_key=gap.role_key or "unknown",
            matching_skills=gap.matching_skills,
            missing_skills=gap.missing_skills,
            recommended_difficulty=gap.recommended_difficulty,
        )
        if gap is not None
        else None
    )

    evidence_snippets = [
        text
        for text in (
            [skill.evidence_text for skill in resume.skills]
            + [p.evidence_text for p in resume.projects]
            + [e.evidence_text for e in resume.experience]
        )
        if text
    ]

    return ResumeInterviewContext(
        resume_id=resume.id,
        candidate_name=resume.candidate_name,
        professional_summary=resume.professional_summary,
        skills=skills,
        projects=projects,
        experience=experience,
        role_readiness=role_readiness,
        recommended_difficulty=gap.recommended_difficulty if gap is not None else None,
        evidence_snippets=evidence_snippets,
    )


async def get_active_resume_context(
    session: AsyncSession, user_id: uuid.UUID
) -> ResumeInterviewContext | None:
    """Returns None if the candidate has no active resume, or their active
    resume hasn't finished processing yet — callers (a future
    StartInterview use case) decide what that means for session creation,
    this function only reports what's actually available.
    """
    resume = await ResumeRepository(session).get_active_for_user_with_children(user_id)
    if resume is None:
        return None
    return build_resume_interview_context(resume)
