"""Interview planning catalog repositories (Database.md §4, Module 4).

Read-heavy — companies/roles/templates are candidate-facing catalog data,
not owned by any one user, so there's no ownership filter here the way
ResumeRepository has. `is_active` filtering happens in the query itself
(not "fetch then check in Python") for the same reason ownership filtering
does in ResumeRepository: it makes "don't show/accept inactive catalog
entries" a property of the query.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.planning import Company, InterviewTemplate, Role, TemplateRound
from app.repositories.base import BaseRepository


class CompanyRepository(BaseRepository[Company]):
    model = Company

    async def list_active(self) -> list[Company]:
        result = await self._session.execute(
            select(Company).where(Company.is_active.is_(True)).order_by(Company.name)
        )
        return list(result.scalars().all())

    async def get_active(self, company_id: uuid.UUID) -> Company | None:
        result = await self._session.execute(
            select(Company).where(Company.id == company_id, Company.is_active.is_(True))
        )
        return result.scalar_one_or_none()


class RoleRepository(BaseRepository[Role]):
    model = Role

    async def list_active(
        self, *, level: str | None = None, company_id: uuid.UUID | None = None
    ) -> list[Role]:
        stmt = select(Role).where(Role.is_active.is_(True))
        if level is not None:
            stmt = stmt.where(Role.level == level)
        if company_id is not None:
            stmt = stmt.where(Role.company_id == company_id)
        result = await self._session.execute(stmt.order_by(Role.title))
        return list(result.scalars().all())

    async def get_active(self, role_id: uuid.UUID) -> Role | None:
        result = await self._session.execute(
            select(Role).where(Role.id == role_id, Role.is_active.is_(True))
        )
        return result.scalar_one_or_none()


class InterviewTemplateRepository(BaseRepository[InterviewTemplate]):
    model = InterviewTemplate

    async def list_active(
        self,
        *,
        role_id: uuid.UUID | None = None,
        company_id: uuid.UUID | None = None,
        mode: str | None = None,
    ) -> list[InterviewTemplate]:
        stmt = (
            select(InterviewTemplate)
            .where(InterviewTemplate.is_active.is_(True))
            .options(selectinload(InterviewTemplate.rounds))
        )
        if role_id is not None:
            stmt = stmt.where(InterviewTemplate.role_id == role_id)
        if company_id is not None:
            stmt = stmt.where(InterviewTemplate.company_id == company_id)
        if mode is not None:
            stmt = stmt.where(InterviewTemplate.mode == mode)
        result = await self._session.execute(stmt.order_by(InterviewTemplate.name))
        return list(result.scalars().all())

    async def get_active_with_rounds(self, template_id: uuid.UUID) -> InterviewTemplate | None:
        stmt = (
            select(InterviewTemplate)
            .where(InterviewTemplate.id == template_id, InterviewTemplate.is_active.is_(True))
            .options(selectinload(InterviewTemplate.rounds))
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id_with_rounds(self, template_id: uuid.UUID) -> InterviewTemplate | None:
        """Unfiltered by is_active — used internally by the planner after
        it has already decided (e.g. re-validating within a transaction)
        rather than by catalog-browsing endpoints.
        """
        stmt = (
            select(InterviewTemplate)
            .where(InterviewTemplate.id == template_id)
            .options(selectinload(InterviewTemplate.rounds))
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()


__all__ = [
    "CompanyRepository",
    "RoleRepository",
    "InterviewTemplateRepository",
    "TemplateRound",
]
