"""Request/response DTOs for the dashboard API (Module 8). Same `*Out`
naming convention as schemas/report.py/coding.py — no request schemas
needed, every endpoint here is a read.
"""

import uuid
from datetime import date, datetime

from pydantic import BaseModel

from app.models.enums import ProgressTrend, SessionStatus


class DashboardOverviewOut(BaseModel):
    interviews_completed: int
    avg_overall_score: float
    trend: ProgressTrend


class SkillProgressOut(BaseModel):
    skill_name: str
    proficiency_score: float
    trend: ProgressTrend
    last_assessed_at: datetime


class CompanyReadinessOut(BaseModel):
    company_id: uuid.UUID
    company_name: str
    readiness_score: float
    last_interview_session_id: uuid.UUID | None
    updated_at: datetime


class ProgressSnapshotOut(BaseModel):
    snapshot_date: date
    interviews_completed: int
    avg_overall_score: float


class HistoryReportSummaryOut(BaseModel):
    id: uuid.UUID
    overall_score: float
    generated_at: datetime


class HistoryItemOut(BaseModel):
    session_id: uuid.UUID
    status: SessionStatus
    created_at: datetime
    completed_at: datetime | None
    # None when this session has no report yet (never completed, or
    # completed but report generation hasn't finished/failed) — never a
    # fabricated placeholder.
    report: HistoryReportSummaryOut | None


class PaginatedHistoryOut(BaseModel):
    items: list[HistoryItemOut]
    total: int
    limit: int
    offset: int
