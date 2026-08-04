"""Interview planning domain — Database.md §4."""

import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, Numeric, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin
from app.models.enums import DifficultyLevel, RoleLevel, RoundType, pg_enum


class Company(Base, UUIDPrimaryKeyMixin, CreatedAtMixin):
    __tablename__ = "companies"

    name: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(Text, unique=True, nullable=False, index=True)
    logo_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    interview_style_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

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
