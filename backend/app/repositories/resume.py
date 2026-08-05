"""Resume domain repositories — Database.md §3, extended Module 3.

Every lookup that can be reached from an API route takes `user_id` and
filters by it in the query itself (not "fetch by id, then check
`.user_id == current_user.id` in Python") — this is what makes ownership
enforcement (module §15/§9) a property of the query, not something a
future caller could forget to check.
"""

import uuid

from sqlalchemy import select, update
from sqlalchemy.orm import selectinload

from app.models.resume import Resume
from app.repositories.base import BaseRepository

_CHILD_RELATIONSHIPS = (
    Resume.education,
    Resume.skills,
    Resume.projects,
    Resume.experience,
    Resume.certifications,
    Resume.achievements,
    Resume.gap_analysis,
)


class ResumeRepository(BaseRepository[Resume]):
    model = Resume

    async def list_by_user(self, user_id: uuid.UUID) -> list[Resume]:
        result = await self._session.execute(
            select(Resume).where(Resume.user_id == user_id).order_by(Resume.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_owned(self, resume_id: uuid.UUID, user_id: uuid.UUID) -> Resume | None:
        result = await self._session.execute(
            select(Resume).where(Resume.id == resume_id, Resume.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_owned_with_children(
        self, resume_id: uuid.UUID, user_id: uuid.UUID
    ) -> Resume | None:
        stmt = (
            select(Resume)
            .where(Resume.id == resume_id, Resume.user_id == user_id)
            .options(*(selectinload(rel) for rel in _CHILD_RELATIONSHIPS))
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_active_for_user(self, user_id: uuid.UUID) -> Resume | None:
        result = await self._session.execute(
            select(Resume).where(Resume.user_id == user_id, Resume.is_active.is_(True))
        )
        return result.scalar_one_or_none()

    async def get_active_for_user_with_children(self, user_id: uuid.UUID) -> Resume | None:
        stmt = (
            select(Resume)
            .where(Resume.user_id == user_id, Resume.is_active.is_(True))
            .options(*(selectinload(rel) for rel in _CHILD_RELATIONSHIPS))
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def deactivate_all_for_user(self, user_id: uuid.UUID) -> None:
        """Clears is_active on every resume this user owns. Called before
        activating a new upload (or promoting the next-most-recent resume
        after a delete) — the partial unique index
        (uq_resumes_one_active_per_user) is what actually enforces "at
        most one active", this just clears the way for the next INSERT/UPDATE.
        """
        await self._session.execute(
            update(Resume).where(Resume.user_id == user_id).values(is_active=False)
        )
        await self._session.flush()

    async def most_recent_other_resume(
        self, user_id: uuid.UUID, exclude_resume_id: uuid.UUID
    ) -> Resume | None:
        result = await self._session.execute(
            select(Resume)
            .where(Resume.user_id == user_id, Resume.id != exclude_resume_id)
            .order_by(Resume.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()
