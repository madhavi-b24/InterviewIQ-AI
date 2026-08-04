"""Report domain — Database.md §7.

report_section_scores is normalized (one row per dimension) rather than
wide nullable columns — a session with no coding round simply has no
`coding` row. See Database.md §7 "Score aggregation" for how overall_score
and section scores are computed.
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UUIDPrimaryKeyMixin
from app.models.enums import ReportSection, ResourceType, Severity, pg_enum


class InterviewReport(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "interview_reports"

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("interview_sessions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    overall_score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    overall_explanation: Mapped[str] = mapped_column(Text, nullable=False)
    summary_text: Mapped[str] = mapped_column(Text, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    section_scores: Mapped[list["ReportSectionScore"]] = relationship(
        back_populates="report", cascade="all, delete-orphan"
    )
    weak_areas: Mapped[list["ReportWeakArea"]] = relationship(
        back_populates="report", cascade="all, delete-orphan"
    )
    strong_areas: Mapped[list["ReportStrongArea"]] = relationship(
        back_populates="report", cascade="all, delete-orphan"
    )
    roadmap: Mapped["LearningRoadmap | None"] = relationship(
        back_populates="report", cascade="all, delete-orphan", uselist=False
    )


class ReportSectionScore(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "report_section_scores"
    __table_args__ = (UniqueConstraint("report_id", "section"),)

    report_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("interview_reports.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    section: Mapped[ReportSection] = mapped_column(
        pg_enum(ReportSection, name="report_section_scores_section_enum"), nullable=False
    )
    score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)

    report: Mapped["InterviewReport"] = relationship(back_populates="section_scores")


class ReportWeakArea(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "report_weak_areas"

    report_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("interview_reports.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    topic: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[Severity] = mapped_column(
        pg_enum(Severity, name="report_weak_areas_severity_enum"), nullable=False
    )
    evidence_text: Mapped[str] = mapped_column(Text, nullable=False)

    report: Mapped["InterviewReport"] = relationship(back_populates="weak_areas")


class ReportStrongArea(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "report_strong_areas"

    report_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("interview_reports.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    topic: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_text: Mapped[str] = mapped_column(Text, nullable=False)

    report: Mapped["InterviewReport"] = relationship(back_populates="strong_areas")


class LearningRoadmap(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "learning_roadmaps"

    report_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("interview_reports.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    report: Mapped["InterviewReport"] = relationship(back_populates="roadmap")
    items: Mapped[list["RoadmapItem"]] = relationship(
        back_populates="roadmap", cascade="all, delete-orphan", order_by="RoadmapItem.sequence_no"
    )


class RoadmapItem(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "roadmap_items"

    roadmap_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("learning_roadmaps.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    topic: Mapped[str] = mapped_column(Text, nullable=False)
    resource_title: Mapped[str] = mapped_column(Text, nullable=False)
    resource_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    resource_type: Mapped[ResourceType] = mapped_column(
        pg_enum(ResourceType, name="roadmap_items_resource_type_enum"), nullable=False
    )
    priority: Mapped[int] = mapped_column(Integer, nullable=False)
    is_completed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False)

    roadmap: Mapped["LearningRoadmap"] = relationship(back_populates="items")
