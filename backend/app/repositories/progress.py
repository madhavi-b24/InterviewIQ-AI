"""Progress-domain repositories (Module 8, Database.md §8). Mirrors
app/repositories/report.py's shape: one file, one repository class per
model, ownership always scoped by `user_id` (never a separate ownership
check layered on afterward — every method here takes user_id directly).

Two of these back a write path invoked once per generated report
(ProgressService.record_session_progress, called from app/jobs/
report_generation.py right after ReportService.generate_report_for_session
succeeds — Module 8's one approved Module 7 integration point) and a read
path the four /dashboard/* endpoints use.
"""

import uuid
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import SessionStatus
from app.models.interview import InterviewSession
from app.models.planning import Company
from app.models.progress import CompanyReadiness, SkillProgress, UserProgressSnapshot
from app.models.report import InterviewReport
from app.repositories.base import BaseRepository


class SkillProgressRepository(BaseRepository[SkillProgress]):
    model = SkillProgress

    async def get_by_user_and_skill(
        self, user_id: uuid.UUID, skill_name: str
    ) -> SkillProgress | None:
        stmt = select(SkillProgress).where(
            SkillProgress.user_id == user_id, SkillProgress.skill_name == skill_name
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_user(self, user_id: uuid.UUID) -> list[SkillProgress]:
        stmt = (
            select(SkillProgress)
            .where(SkillProgress.user_id == user_id)
            .order_by(SkillProgress.skill_name)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


class CompanyReadinessRepository(BaseRepository[CompanyReadiness]):
    model = CompanyReadiness

    async def get_by_user_and_company(
        self, user_id: uuid.UUID, company_id: uuid.UUID
    ) -> CompanyReadiness | None:
        stmt = select(CompanyReadiness).where(
            CompanyReadiness.user_id == user_id, CompanyReadiness.company_id == company_id
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_user_with_company_name(
        self, user_id: uuid.UUID
    ) -> list[tuple[CompanyReadiness, str]]:
        stmt = (
            select(CompanyReadiness, Company.name)
            .join(Company, CompanyReadiness.company_id == Company.id)
            .where(CompanyReadiness.user_id == user_id)
            .order_by(Company.name)
        )
        result = await self._session.execute(stmt)
        return [(row[0], row[1]) for row in result.all()]


class UserProgressSnapshotRepository(BaseRepository[UserProgressSnapshot]):
    model = UserProgressSnapshot

    async def get_by_user_and_date(
        self, user_id: uuid.UUID, snapshot_date: date
    ) -> UserProgressSnapshot | None:
        stmt = select(UserProgressSnapshot).where(
            UserProgressSnapshot.user_id == user_id,
            UserProgressSnapshot.snapshot_date == snapshot_date,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_latest_for_user(self, user_id: uuid.UUID) -> UserProgressSnapshot | None:
        stmt = (
            select(UserProgressSnapshot)
            .where(UserProgressSnapshot.user_id == user_id)
            .order_by(UserProgressSnapshot.snapshot_date.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_user(self, user_id: uuid.UUID) -> list[UserProgressSnapshot]:
        """Oldest-first — the natural order for a trend-chart timeline."""
        stmt = (
            select(UserProgressSnapshot)
            .where(UserProgressSnapshot.user_id == user_id)
            .order_by(UserProgressSnapshot.snapshot_date.asc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_and_average_for_user(self, user_id: uuid.UUID) -> tuple[int, float]:
        """(interviews_completed, avg_overall_score) across every completed
        session with a report for this user, recomputed fresh each call —
        the pair `user_progress_snapshots.interviews_completed`/
        `avg_overall_score` get upserted from (Database.md §8: "written
        whenever a report is generated"). The explicit
        `InterviewSession.status == COMPLETED` filter is a defensive
        invariant, not strictly load-bearing today (a report only ever
        exists for a session that was COMPLETED at generation time — see
        ReportService.generate_report_for_session) — kept so an incomplete
        session can never contribute here even if that invariant ever
        changes.
        """
        stmt = (
            select(func.count(InterviewReport.id), func.avg(InterviewReport.overall_score))
            .join(InterviewSession, InterviewReport.session_id == InterviewSession.id)
            .where(
                InterviewSession.user_id == user_id,
                InterviewSession.status == SessionStatus.COMPLETED,
            )
        )
        result = await self._session.execute(stmt)
        count, avg = result.one()
        return (count or 0, float(avg) if avg is not None else 0.0)


class InterviewHistoryRepository:
    """Not a BaseRepository[Model] — this reads two existing Module 4/5/7
    tables (`interview_sessions` LEFT JOIN `interview_reports`) rather than
    owning a table of its own. Kept in this file rather than added to
    app/repositories/interview.py (Module 5) — Module 8's only approved
    Module 1-7 touch point is the one call in app/jobs/report_generation.py.
    `InterviewSession` has no ORM relationship to `InterviewReport` (a
    session might have zero or one — the FK is on the report side), so
    this is a plain join, not a selectinload chain.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_for_user(
        self, user_id: uuid.UUID, *, limit: int, offset: int
    ) -> tuple[list[tuple[InterviewSession, InterviewReport | None]], int]:
        base = select(InterviewSession).where(InterviewSession.user_id == user_id)

        count_stmt = select(func.count()).select_from(base.subquery())
        total = (await self._session.execute(count_stmt)).scalar_one()

        stmt = (
            select(InterviewSession, InterviewReport)
            .outerjoin(InterviewReport, InterviewReport.session_id == InterviewSession.id)
            .where(InterviewSession.user_id == user_id)
            .order_by(InterviewSession.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        rows = [(row[0], row[1]) for row in result.all()]
        return rows, total
