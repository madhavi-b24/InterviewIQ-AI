"""Progress domain — Database.md §8."""

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKeyMixin
from app.models.enums import ProgressTrend, pg_enum


class SkillProgress(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "skill_progress"
    __table_args__ = (UniqueConstraint("user_id", "skill_name"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    skill_name: Mapped[str] = mapped_column(Text, nullable=False)
    proficiency_score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    trend: Mapped[ProgressTrend] = mapped_column(
        pg_enum(ProgressTrend, name="skill_progress_trend_enum"), nullable=False
    )
    last_assessed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CompanyReadiness(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "company_readiness"
    __table_args__ = (UniqueConstraint("user_id", "company_id"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    readiness_score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    last_interview_session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("interview_sessions.id", ondelete="SET NULL"), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class UserProgressSnapshot(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "user_progress_snapshots"
    __table_args__ = (UniqueConstraint("user_id", "snapshot_date"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    interviews_completed: Mapped[int] = mapped_column(Integer, nullable=False)
    avg_overall_score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)
