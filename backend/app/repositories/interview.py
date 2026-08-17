"""Interview session repository (Database.md §5, Module 4 — planning only;
execution fields/methods are Module 5's).

Every read method takes `user_id` and filters by it in the query itself —
same ownership-enforcement pattern as ResumeRepository (module §13): a
cross-user interview id resolves as "not found" at the query level, never
as "found, then rejected in Python".
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.interview import InterviewSession
from app.repositories.base import BaseRepository


class InterviewSessionRepository(BaseRepository[InterviewSession]):
    model = InterviewSession

    async def get_owned(self, session_id: uuid.UUID, user_id: uuid.UUID) -> InterviewSession | None:
        stmt = (
            select(InterviewSession)
            .where(InterviewSession.id == session_id, InterviewSession.user_id == user_id)
            .options(selectinload(InterviewSession.rounds))
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_owned(
        self, user_id: uuid.UUID, *, status: str | None = None
    ) -> list[InterviewSession]:
        stmt = select(InterviewSession).where(InterviewSession.user_id == user_id)
        if status is not None:
            stmt = stmt.where(InterviewSession.status == status)
        stmt = stmt.order_by(InterviewSession.created_at.desc())
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
