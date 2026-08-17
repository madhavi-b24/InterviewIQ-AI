"""Interview planning domain — Database.md §4."""

import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, Numeric, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin
from app.models.enums import DifficultyLevel, InterviewMode, RoleLevel, RoundType, pg_enum


class Company(Base, UUIDPrimaryKeyMixin, CreatedAtMixin):
    __tablename__ = "companies"

    name: Mapped[str] = mapped_column(Text, nullable=False)
    # Doubles as the stable catalog "key" module §2 asks for — a company has
    # exactly one natural identifier, so a separate `key` column would only
    # duplicate `slug` under a different name.
    slug: Mapped[str] = mapped_column(Text, unique=True, nullable=False, index=True)
    logo_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Grounding context fed to the future Question Generator Agent. Module 4
    # requirement: these are InterviewIQ preparation profiles based on
    # public/general interview patterns — NEVER a claim to reproduce a real
    # company's actual/confidential process. Enforced by seed-data content
    # and documented in backend/README.md, not by a schema constraint.
    interview_style_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Module 4 — inactive companies are excluded from catalog listings and
    # rejected as a plan target (module §16), without ever deleting history
    # that existing interview_sessions/templates still reference.
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    roles: Mapped[list["Role"]] = relationship(back_populates="company")
    templates: Mapped[list["InterviewTemplate"]] = relationship(back_populates="company")


class Role(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "roles"

    company_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    level: Mapped[RoleLevel] = mapped_column(
        pg_enum(RoleLevel, name="roles_level_enum"), nullable=False
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Module 4 — the canonical link back to Module 3's internal competency
    # profiles (app/services/resume/role_profiles.json — "software_engineer",
    # "backend_engineer", "ai_engineer", "ml_engineer", "data_engineer").
    # One taxonomy, not two: AUTO difficulty and personalization both key off
    # this instead of re-deriving a role identity from `title`. Nullable
    # because a role row with no InterviewIQ competency-profile equivalent
    # can still exist (e.g. a future company-specific title), it just can't
    # participate in resume-driven AUTO difficulty/personalization.
    role_key: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    company: Mapped["Company | None"] = relationship(back_populates="roles")
    templates: Mapped[list["InterviewTemplate"]] = relationship(back_populates="role")


class InterviewTemplate(Base, UUIDPrimaryKeyMixin, CreatedAtMixin):
    __tablename__ = "interview_templates"

    company_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="SET NULL"), nullable=True
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roles.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    default_difficulty: Mapped[DifficultyLevel] = mapped_column(
        pg_enum(DifficultyLevel, name="interview_templates_default_difficulty_enum"),
        nullable=False,
    )
    # Module 4 — which candidate-facing mode this named round plan
    # represents (e.g. "Google SWE — Full Mock" -> FULL_MOCK). A plan
    # request either omits `mode` (inherits this) or must match it exactly
    # — templates are never dynamically re-filtered per mode at plan time.
    mode: Mapped[InterviewMode] = mapped_column(
        pg_enum(InterviewMode, name="interview_templates_mode_enum"),
        nullable=False,
        default=InterviewMode.FULL_MOCK,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    company: Mapped["Company | None"] = relationship(back_populates="templates")
    role: Mapped["Role"] = relationship(back_populates="templates")
    rounds: Mapped[list["TemplateRound"]] = relationship(
        back_populates="template",
        cascade="all, delete-orphan",
        order_by="TemplateRound.sequence_no",
    )


class TemplateRound(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "template_rounds"
    __table_args__ = (UniqueConstraint("template_id", "sequence_no"),)

    template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("interview_templates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    round_type: Mapped[RoundType] = mapped_column(
        pg_enum(RoundType, name="template_rounds_round_type_enum"), nullable=False
    )
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False)
    weight: Mapped[float] = mapped_column(Numeric(4, 2), nullable=False)
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    difficulty_override: Mapped[DifficultyLevel | None] = mapped_column(
        pg_enum(DifficultyLevel, name="template_rounds_difficulty_override_enum"), nullable=True
    )

    template: Mapped["InterviewTemplate"] = relationship(back_populates="rounds")
