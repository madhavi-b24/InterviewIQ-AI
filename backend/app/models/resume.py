"""Resume domain — Database.md §3, extended additively in Module 3
(Resume Intelligence) with evidence/provenance, skill categorization,
certifications/achievements, versioning, and role-readiness fields.

Every additive column here is nullable or defaulted so the Module 1
baseline migration's rows (none exist yet in practice, but the principle
holds) never need backfilling.
"""

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Numeric, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin
from app.models.enums import (
    DifficultyLevel,
    ParsedStatus,
    ProficiencyHint,
    SkillCategory,
    SkillSource,
    pg_enum,
)


class Resume(Base, UUIDPrimaryKeyMixin, CreatedAtMixin):
    __tablename__ = "resumes"
    __table_args__ = (
        # At most one active resume per user (versioning, module §10) —
        # mirrored here so `alembic check`/autogenerate see the migration's
        # partial index as already satisfied instead of flagging drift.
        Index(
            "uq_resumes_one_active_per_user",
            "user_id",
            unique=True,
            postgresql_where=text("is_active"),
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Server-generated storage key (app/storage/), never a client filename
    # and never a filesystem path — see LocalResumeStorage.
    file_url: Mapped[str] = mapped_column(Text, nullable=False)
    original_filename: Mapped[str] = mapped_column(Text, nullable=False)
    parsed_status: Mapped[ParsedStatus] = mapped_column(
        pg_enum(ParsedStatus, name="resumes_parsed_status_enum"),
        nullable=False,
        default=ParsedStatus.PENDING,
    )
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- Module 3 additive columns ---------------------------------------
    # Versioning (Roadmap.md Module 3 §10): exactly one resume per user is
    # "active" — enforced by a partial unique index in the migration, not
    # just application logic. Historical (inactive) resumes are retained,
    # never deleted on new upload.
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Populated only when parsed_status = failed — human-readable reason
    # (e.g. "scanned/image-only PDF", "AI analysis timed out"). Distinct
    # processing sub-states (extracting/analyzing) are communicated through
    # this message rather than a new enum value, since Database.md's
    # parsed_status enum (pending/processing/done/failed) is reused as-is.
    processing_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    mime_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_size_bytes: Mapped[int | None] = mapped_column(nullable=True)
    content_sha256: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Raw text, split per detected section (Summary/Education/Skills/...) —
    # kept separate from the structured tables below per the module's
    # "store raw text separately from structured analysis" requirement.
    detected_sections: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    candidate_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    professional_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    embeddings_indexed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    skills: Mapped[list["ResumeSkill"]] = relationship(
        back_populates="resume", cascade="all, delete-orphan"
    )
    projects: Mapped[list["ResumeProject"]] = relationship(
        back_populates="resume", cascade="all, delete-orphan"
    )
    experience: Mapped[list["ResumeExperience"]] = relationship(
        back_populates="resume", cascade="all, delete-orphan"
    )
    education: Mapped[list["ResumeEducation"]] = relationship(
        back_populates="resume", cascade="all, delete-orphan"
    )
    certifications: Mapped[list["ResumeCertification"]] = relationship(
        back_populates="resume", cascade="all, delete-orphan"
    )
    achievements: Mapped[list["ResumeAchievement"]] = relationship(
        back_populates="resume", cascade="all, delete-orphan"
    )
    gap_analysis: Mapped["ResumeGapAnalysis | None"] = relationship(
        back_populates="resume", cascade="all, delete-orphan", uselist=False
    )


class ResumeSkill(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "resume_skills"

    resume_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("resumes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Canonical/normalized name (app/services/resume/skill_normalization.py),
    # e.g. "JavaScript", "PostgreSQL" — what the rest of the app queries by.
    skill_name: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    proficiency_hint: Mapped[ProficiencyHint | None] = mapped_column(
        pg_enum(ProficiencyHint, name="resume_skills_proficiency_hint_enum"), nullable=True
    )
    source: Mapped[SkillSource] = mapped_column(
        pg_enum(SkillSource, name="resume_skills_source_enum"), nullable=False
    )
    category: Mapped[SkillCategory | None] = mapped_column(
        pg_enum(SkillCategory, name="resume_skills_category_enum"), nullable=True
    )
    # As detected on the resume before normalization, e.g. "JS" — kept so
    # normalization is inspectable/correctable, not a silent lossy rewrite.
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Provenance (module requirement §6): the resume sentence/fragment this
    # skill was extracted from, so a future interview question can be
    # grounded in what the candidate actually claimed.
    evidence_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)

    resume: Mapped["Resume"] = relationship(back_populates="skills")


class ResumeProject(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "resume_projects"

    resume_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("resumes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    technologies: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    responsibilities: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    outcomes: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    evidence_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    resume: Mapped["Resume"] = relationship(back_populates="projects")


class ResumeExperience(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "resume_experience"

    resume_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("resumes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    company: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    technologies: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    responsibilities: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    evidence_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    resume: Mapped["Resume"] = relationship(back_populates="experience")


class ResumeEducation(Base, UUIDPrimaryKeyMixin):
    """Not in Database.md's original Module 1 schema (which has no
    education entity at all) — added in Module 3 for the structured
    education extraction this module's §5 requires, mirroring the shape
    of the pre-existing resume_experience table.
    """

    __tablename__ = "resume_education"

    resume_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("resumes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    institution: Mapped[str] = mapped_column(Text, nullable=False)
    degree: Mapped[str | None] = mapped_column(Text, nullable=True)
    field_of_study: Mapped[str | None] = mapped_column(Text, nullable=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    evidence_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    resume: Mapped["Resume"] = relationship(back_populates="education")


class ResumeCertification(Base, UUIDPrimaryKeyMixin):
    """Not in Database.md's original Module 1 schema — added in Module 3
    (Resume Intelligence) for structured certification extraction
    (Features.md §2 / this module's §5), mirroring the shape of the
    existing resume_* child tables.
    """

    __tablename__ = "resume_certifications"

    resume_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("resumes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    issuer: Mapped[str | None] = mapped_column(Text, nullable=True)
    issued_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    evidence_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    resume: Mapped["Resume"] = relationship(back_populates="certifications")


class ResumeAchievement(Base, UUIDPrimaryKeyMixin):
    """Added in Module 3 alongside ResumeCertification — see its docstring."""

    __tablename__ = "resume_achievements"

    resume_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("resumes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    resume: Mapped["Resume"] = relationship(back_populates="achievements")


class ResumeGapAnalysis(Base, UUIDPrimaryKeyMixin):
    """Role-readiness + explainable difficulty recommendation (module §11,
    §12). Database.md's ER diagram already models this as at most one row
    per resume (`resumes ||--o| resume_gap_analysis`) — enforced here via
    a unique constraint on resume_id, and the service re-generates
    (replaces) this single row rather than accumulating history per role.
    """

    __tablename__ = "resume_gap_analysis"

    resume_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("resumes.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    target_role_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roles.id", ondelete="SET NULL"), nullable=True
    )
    # Internal InterviewIQ competency-profile key (app/services/resume/role_profiles.py),
    # e.g. "backend_engineer" — used instead of target_role_id while
    # Module 4's `roles` table isn't seeded yet. Both are kept so a future
    # Module 4 role can be attached without another migration.
    role_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    missing_skills: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    matching_skills: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    strengths: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    focus_areas: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    recommended_difficulty: Mapped[DifficultyLevel] = mapped_column(
        pg_enum(DifficultyLevel, name="resume_gap_analysis_recommended_difficulty_enum"),
        nullable=False,
    )
    # Explainable signals behind recommended_difficulty (module §12) — never
    # an arbitrary LLM guess, see app/services/resume/readiness.py.
    difficulty_reasons: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    confidence: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    resume: Mapped["Resume"] = relationship(back_populates="gap_analysis")
