"""Interview-planning catalog API — API.md §3, Module 4. Thin per
Architecture.md §4: parses the request, calls exactly one CatalogService
method, shapes the response. Every endpoint requires authentication
(candidates must be logged in to browse, per this project's existing
"required" auth convention for all non-auth routes) but is not
ownership-scoped — the catalog is shared, read-only reference data.
"""

import uuid

from fastapi import APIRouter, Query

from app.api.deps import CatalogServiceDep, CurrentUser
from app.models.enums import InterviewMode, RoleLevel
from app.schemas.planning import CompanyOut, RoleOut, TemplateDetailOut, TemplateSummaryOut

router = APIRouter(tags=["planning"])


@router.get("/companies")
async def list_companies(_: CurrentUser, catalog: CatalogServiceDep) -> list[CompanyOut]:
    companies = await catalog.list_companies()
    return [CompanyOut.model_validate(c) for c in companies]


@router.get("/companies/{company_id}/roles")
async def list_company_roles(
    company_id: uuid.UUID, _: CurrentUser, catalog: CatalogServiceDep
) -> list[RoleOut]:
    roles = await catalog.list_company_roles(company_id)
    return [RoleOut.model_validate(r) for r in roles]


@router.get("/roles")
async def list_roles(
    _: CurrentUser,
    catalog: CatalogServiceDep,
    level: RoleLevel | None = Query(default=None),
) -> list[RoleOut]:
    roles = await catalog.list_roles(level=level.value if level else None)
    return [RoleOut.model_validate(r) for r in roles]


@router.get("/roles/{role_id}/templates")
async def list_role_templates(
    role_id: uuid.UUID,
    _: CurrentUser,
    catalog: CatalogServiceDep,
    company_id: uuid.UUID | None = Query(default=None),
    mode: InterviewMode | None = Query(default=None),
) -> list[TemplateSummaryOut]:
    templates = await catalog.list_templates(
        role_id=role_id, company_id=company_id, mode=mode.value if mode else None
    )
    return [TemplateSummaryOut.model_validate(t) for t in templates]


@router.get("/templates/{template_id}")
async def get_template(
    template_id: uuid.UUID, _: CurrentUser, catalog: CatalogServiceDep
) -> TemplateDetailOut:
    template = await catalog.get_template(template_id)
    return TemplateDetailOut.model_validate(template)
