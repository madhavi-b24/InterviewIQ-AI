"""Resume domain — Database.md §3."""

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin
from app.models.enums import DifficultyLevel, ParsedStatus, ProficiencyHint, SkillSource, pg_enum


class Resume(Base, UUIDPrimaryKeyMixin, CreatedAtMixin):
    __tablename__ = "resumes"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    file_url: Mapped[str] = mapped_column(Text, nullable=False)
    original_filename: Mapped[str] = mapped_column(Text, nullable=False)
    parsed_status: Mapped[ParsedStatus] = mapped_column(
        pg_enum(ParsedStatus, name="resumes_parsed_status_enum"),
        nullable=False,
        default=ParsedStatus.PENDING,
    )
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    skills: Mapped[list["ResumeSkill"]] = relationship(
        back_populates="resume", cascade="all, delete-orphan"
    )
    projects: Mapped[list["ResumeProject"]] = relationship(
        back_populates="resume", cascade="all, delete-orphan"
    )
    experience: Mapped[list["ResumeExperience"]] = relationship(
        back_populates="resume", cascade="all, delete-orphan"
    )
    gap_analyses: Mapped[list["ResumeGapAnalysis"]] = relationship(
        back_populates="resume", cascade="all, delete-orphan"
    )


class ResumeSkill(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "resume_skills"

    resume_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("resumes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    skill_name: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    proficiency_hint: Mapped[ProficiencyHint | None] = mapped_column(
        pg_enum(ProficiencyHint, name="resume_skills_proficiency_hint_enum"), nullable=True
    )
    source: Mapped[SkillSource] = mapped_column(
        pg_enum(SkillSource, name="resume_skills_source_enum"), nullable=False
    )

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

    resume: Mapped["Resume"] = relationship(back_populates="experience")


class ResumeGapAnalysis(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "resume_gap_analysis"

    resume_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("resumes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    target_role_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roles.id", ondelete="SET NULL"), nullable=True
    )
    missing_skills: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    recommended_difficulty: Mapped[DifficultyLevel] = mapped_column(
        pg_enum(DifficultyLevel, name="resume_gap_analysis_recommended_difficulty_enum"),
        nullable=False,
    )
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    resume: Mapped["Resume"] = relationship(back_populates="gap_analyses")
