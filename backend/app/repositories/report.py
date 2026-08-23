"""Report/roadmap repositories (Module 7, Database.md §7). Mirrors
app/repositories/coding.py's shape: one file per domain, a repository
class per model, ownership checks done via an explicit join back to
InterviewSession.user_id rather than the caller pre-fetching an owned
parent first — the API layer (app/api/v1/reports.py) has no session_id
in scope for the roadmap/roadmap-item endpoints, only a report_id/
roadmap_item_id, so the join has to start there.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.interview import InterviewSession
from app.models.report import InterviewReport, LearningRoadmap, RoadmapItem
from app.repositories.base import BaseRepository

# Eager-load the whole report graph in one round trip — the API response
# needs section_scores/weak_areas/strong_areas/roadmap.items and nothing
# here is ever lazy-loaded (MissingGreenlet under asyncpg — module §14's
# established discipline, same reasoning app/repositories/coding.py's
# _SUBMISSION_LOAD_OPTIONS already documents).
_REPORT_LOAD_OPTIONS = (
    selectinload(InterviewReport.section_scores),
    selectinload(InterviewReport.weak_areas),
    selectinload(InterviewReport.strong_areas),
    selectinload(InterviewReport.roadmap).selectinload(LearningRoadmap.items),
)


class InterviewReportRepository(BaseRepository[InterviewReport]):
    model = InterviewReport

    async def get_by_session_id(self, session_id: uuid.UUID) -> InterviewReport | None:
        """Unqualified by ownership — used for the idempotency pre-check in
        ReportService.generate_report_for_session, which already only ever
        runs against a session_id the caller (the job) derived from a
        genuine SessionStatus.COMPLETED transition, never from user input.
        """
        stmt = (
            select(InterviewReport)
            .where(InterviewReport.session_id == session_id)
            .options(*_REPORT_LOAD_OPTIONS)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_owned_by_session(
        self, session_id: uuid.UUID, user_id: uuid.UUID
    ) -> InterviewReport | None:
        stmt = (
            select(InterviewReport)
            .join(InterviewSession, InterviewReport.session_id == InterviewSession.id)
            .where(InterviewReport.session_id == session_id, InterviewSession.user_id == user_id)
            .options(*_REPORT_LOAD_OPTIONS)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_owned_roadmap_by_report_id(
        self, report_id: uuid.UUID, user_id: uuid.UUID
    ) -> LearningRoadmap | None:
        stmt = (
            select(LearningRoadmap)
            .join(InterviewReport, LearningRoadmap.report_id == InterviewReport.id)
            .join(InterviewSession, InterviewReport.session_id == InterviewSession.id)
            .where(LearningRoadmap.report_id == report_id, InterviewSession.user_id == user_id)
            .options(selectinload(LearningRoadmap.items))
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()


class RoadmapItemRepository(BaseRepository[RoadmapItem]):
    model = RoadmapItem

    async def get_owned_by_id(self, item_id: uuid.UUID, user_id: uuid.UUID) -> RoadmapItem | None:
        stmt = (
            select(RoadmapItem)
            .join(LearningRoadmap, RoadmapItem.roadmap_id == LearningRoadmap.id)
            .join(InterviewReport, LearningRoadmap.report_id == InterviewReport.id)
            .join(InterviewSession, InterviewReport.session_id == InterviewSession.id)
            .where(RoadmapItem.id == item_id, InterviewSession.user_id == user_id)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()
