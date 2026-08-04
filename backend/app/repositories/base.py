"""Generic CRUD repository, per Architecture.md §4 — "one repository class
per aggregate root, only place raw queries live."

Concrete repositories (UserRepository, InterviewSessionRepository, ...) are
added starting with the module that first needs feature-specific queries
(e.g. `get_by_email`) — that query logic belongs to the feature, not to
this scaffold. Subclass BaseRepository and add methods as needed:

    class UserRepository(BaseRepository[User]):
        async def get_by_email(self, email: str) -> User | None:
            result = await self._session.execute(select(User).where(User.email == email))
            return result.scalar_one_or_none()
"""

import uuid
from typing import Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    model: type[ModelT]

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, id_: uuid.UUID) -> ModelT | None:
        return await self._session.get(self.model, id_)

    async def add(self, instance: ModelT) -> ModelT:
        self._session.add(instance)
        await self._session.flush()
        return instance

    async def list_all(self) -> list[ModelT]:
        result = await self._session.execute(select(self.model))
        return list(result.scalars().all())
