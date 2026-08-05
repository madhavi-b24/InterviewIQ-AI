"""Request/response DTOs for the Resume Intelligence API (module §16).

Deliberately never includes `file_url` / any storage locator — module §2
("do not expose filesystem paths") extends here to not exposing the
storage backend's logical key either, since it's still an internal
implementation detail no client needs.
"""

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import DifficultyLevel, ParsedStatus, SkillCategory


class ResumeSummary(BaseModel):
    """POST /resumes and GET /resumes list item — no structured analysis,
    just enough to render a resume list / poll processing status.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    original_filename: str
    parsed_status: ParsedStatus
    processing_error: str | None
    is_active: bool
    created_at: datetime


class ResumeDetail(ResumeSummary):
    """GET /resumes/{id} — adds the top-level fields that don't need a
    child-table join.
    """

    candidate_name: str | None
    professional_summary: str | None
    embeddings_indexed_at: datetime | None


class SkillOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str = Field(validation_alias="skill_name")
    category: SkillCategory | None
    source: str
    raw_text: str | None
    evidence: str | None = Field(validation_alias="evidence_text")
    confidence: float | None


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    title: str
    description: str | None
    technologies: list[str]
    responsibilities: list[str]
    outcomes: list[str]
    start_date: date | None
    end_date: date | None
    evidence: str | None = Field(validation_alias="evidence_text")


class ExperienceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    company: str
    title: str
    description: str | None
    technologies: list[str]
    responsibilities: list[str]
    start_date: date | None
    end_date: date | None
    evidence: str | None = Field(validation_alias="evidence_text")


class EducationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    institution: str
    degree: str | None
    field_of_study: str | None
    start_date: date | None
    end_date: date | None
    evidence: str | None = Field(validation_alias="evidence_text")


class CertificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    issuer: str | None
    issued_date: date | None
    evidence: str | None = Field(validation_alias="evidence_text")


class AchievementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    description: str
    evidence: str | None = Field(validation_alias="evidence_text")


class ResumeAnalysisResponse(BaseModel):
    """GET /resumes/{id}/analysis. Always returns whatever structured data
    exists — if parsed_status=failed after raw text was already extracted,
    the lists below may simply be empty rather than the endpoint erroring,
    per module §9 ("preserve the successfully extracted data").
    """

    resume_id: uuid.UUID
    parsed_status: ParsedStatus
    processing_error: str | None
    candidate_name: str | None
    professional_summary: str | None
    detected_sections: list[str]
    education: list[EducationOut]
    skills: list[SkillOut]
    projects: list[ProjectOut]
    experience: list[ExperienceOut]
    certifications: list[CertificationOut]
    achievements: list[AchievementOut]


class GapAnalysisRequest(BaseModel):
    """Deviates from API.md's documented `{ "target_role_id": uuid }` body
    — Module 4's `roles` table isn't seeded yet, so this targets an
    internal InterviewIQ competency profile by key instead (module §11).
    `target_role_id` is accepted too, for forward-compatibility once
    Module 4 exists, but is not resolved to anything yet.
    """

    role_key: str = Field(
        description="e.g. 'backend_engineer' — see GET-able role key list in docs"
    )
    target_role_id: uuid.UUID | None = None

    @field_validator("role_key")
    @classmethod
    def role_key_not_blank(cls, value: str) -> str:
        value = value.strip().lower()
        if not value:
            raise ValueError("role_key must not be blank")
        return value


_LEVEL_LABELS = {
    DifficultyLevel.EASY: "Beginner",
    DifficultyLevel.MEDIUM: "Intermediate",
    DifficultyLevel.HARD: "Advanced",
}


class RoleReadinessResponse(BaseModel):
    resume_id: uuid.UUID
    role_key: str
    role_label: str
    matching_skills: list[str]
    missing_skills: list[str]
    strengths: list[str]
    focus_areas: list[str]
    recommended_difficulty: DifficultyLevel
    recommended_level_label: str
    confidence: float | None
    reasons: list[str]
    explanation: str | None
    generated_at: datetime

    @staticmethod
    def level_label(level: DifficultyLevel) -> str:
        return _LEVEL_LABELS[level]
