"""CatalogService — read-only use-case layer over the planning catalog
(API.md §3, Module 4). Thin on purpose: every method is one repository
call plus, where relevant, a not-found translation — there's no business
rule beyond "only active rows are browsable/selectable" (module §16),
which the repositories already enforce in-query.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.planning import Company, InterviewTemplate, Role
from app.repositories.planning import CompanyRepository, InterviewTemplateRepository, RoleRepository


class CatalogService:
    def __init__(self, session: AsyncSession) -> None:
        self._companies = CompanyRepository(session)
        self._roles = RoleRepository(session)
        self._templates = InterviewTemplateRepository(session)

    async def list_companies(self) -> list[Company]:
        return await self._companies.list_active()

    async def get_company(self, company_id: uuid.UUID) -> Company:
        company = await self._companies.get_active(company_id)
        if company is None:
            raise NotFoundError("company not found", code="COMPANY_NOT_FOUND")
        return company

    async def list_roles(
        self, *, level: str | None = None, company_id: uuid.UUID | None = None
    ) -> list[Role]:
        return await self._roles.list_active(level=level, company_id=company_id)

    async def list_company_roles(self, company_id: uuid.UUID) -> list[Role]:
        await self.get_company(company_id)  # 404s if missing/inactive
        return await self._roles.list_active(company_id=company_id)

    async def list_templates(
        self,
        *,
        role_id: uuid.UUID,
        company_id: uuid.UUID | None = None,
        mode: str | None = None,
    ) -> list[InterviewTemplate]:
        role = await self._roles.get_active(role_id)
        if role is None:
            raise NotFoundError("role not found", code="ROLE_NOT_FOUND")
        return await self._templates.list_active(role_id=role_id, company_id=company_id, mode=mode)

    async def get_template(self, template_id: uuid.UUID) -> InterviewTemplate:
        template = await self._templates.get_active_with_rounds(template_id)
        if template is None:
            raise NotFoundError("interview template not found", code="TEMPLATE_NOT_FOUND")
        return template
