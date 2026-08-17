"""Module 4 — idempotent MVP catalog seeding (module §14, §15).

Deliberately a plain, callable service function rather than migration data
logic ("avoid seeding data through fragile migration logic if the
architecture has a better startup/seed mechanism" — module §14). The
catalog lives in data/catalog.json; this module only knows how to upsert
it, so adding a company/role/template later is a data change, never a
code change.

Idempotency strategy (safe to call on every app startup or from a script,
any number of times):
- Companies matched by their existing unique `slug`.
- Roles have no natural DB-level unique constraint (a role_key can
  legitimately repeat across companies), so they're matched by the
  in-memory (company_id, role_key, title) tuple from the JSON's
  `natural_key` bookkeeping.
- Templates matched by (company_id, role_id, name) — also not
  DB-unique-constrained, same reasoning.
- Template rounds are upserted by (template_id, sequence_no) — the
  actual DB unique constraint — never blindly deleted-and-recreated,
  because interview_rounds.template_round_id is an ON DELETE RESTRICT FK:
  once a real interview has been planned from a round, deleting that
  round out from under it must fail loudly, not silently cascade. A
  round removed from catalog.json is only deleted if nothing references
  it yet; otherwise the deletion is skipped and logged.
"""

import json
import uuid
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.enums import DifficultyLevel, InterviewMode, RoleLevel, RoundType
from app.models.planning import Company, InterviewTemplate, Role, TemplateRound

logger = get_logger(__name__)

_CATALOG_PATH = Path(__file__).parent / "data" / "catalog.json"


class _RoundSeed(BaseModel):
    round_type: RoundType
    sequence_no: int
    weight: Decimal
    is_required: bool = True
    difficulty_override: DifficultyLevel | None = None


class _CompanySeed(BaseModel):
    slug: str
    name: str
    logo_url: str | None = None
    interview_style_notes: str | None = None
    is_active: bool = True


class _RoleSeed(BaseModel):
    natural_key: str
    company_slug: str | None
    role_key: str | None
    title: str
    level: RoleLevel
    description: str | None = None
    is_active: bool = True


class _TemplateSeed(BaseModel):
    natural_key: str
    company_slug: str | None
    role_natural_key: str
    name: str
    description: str | None = None
    mode: InterviewMode
    default_difficulty: DifficultyLevel
    is_active: bool = True
    rounds: list[_RoundSeed]


class _CatalogSeed(BaseModel):
    companies: list[_CompanySeed]
    roles: list[_RoleSeed]
    templates: list[_TemplateSeed]


@lru_cache
def _load_catalog() -> _CatalogSeed:
    raw = json.loads(_CATALOG_PATH.read_text(encoding="utf-8"))
    raw.pop("_comment", None)
    return _CatalogSeed.model_validate(raw)


async def seed_catalog(session: AsyncSession) -> dict[str, int]:
    """Upserts every company/role/template/round in data/catalog.json.
    Returns a small summary dict for logging/CLI output. Commits once at
    the end — the whole catalog seeds atomically, or not at all.
    """
    catalog = _load_catalog()
    counts = {"companies": 0, "roles": 0, "templates": 0, "rounds": 0}

    companies_by_slug = await _upsert_companies(session, catalog.companies)
    counts["companies"] = len(companies_by_slug)

    roles_by_natural_key = await _upsert_roles(session, catalog.roles, companies_by_slug)
    counts["roles"] = len(roles_by_natural_key)

    template_count, round_count = await _upsert_templates(
        session, catalog.templates, companies_by_slug, roles_by_natural_key
    )
    counts["templates"] = template_count
    counts["rounds"] = round_count

    await session.commit()
    logger.info("catalog.seeded", **counts)
    return counts


async def _upsert_companies(session: AsyncSession, seeds: list[_CompanySeed]) -> dict[str, Company]:
    result = await session.execute(select(Company))
    existing = {c.slug: c for c in result.scalars().all()}

    by_slug: dict[str, Company] = {}
    for seed in seeds:
        company = existing.get(seed.slug)
        if company is None:
            company = Company(
                slug=seed.slug,
                name=seed.name,
                logo_url=seed.logo_url,
                interview_style_notes=seed.interview_style_notes,
                is_active=seed.is_active,
            )
            session.add(company)
        else:
            company.name = seed.name
            company.logo_url = seed.logo_url
            company.interview_style_notes = seed.interview_style_notes
            company.is_active = seed.is_active
        by_slug[seed.slug] = company

    await session.flush()
    return by_slug


async def _upsert_roles(
    session: AsyncSession, seeds: list[_RoleSeed], companies_by_slug: dict[str, Company]
) -> dict[str, Role]:
    result = await session.execute(select(Role))
    existing_roles = list(result.scalars().all())

    by_natural_key: dict[str, Role] = {}
    for seed in seeds:
        company = companies_by_slug[seed.company_slug] if seed.company_slug else None
        company_id = company.id if company else None
        match = next(
            (
                r
                for r in existing_roles
                if r.company_id == company_id
                and r.role_key == seed.role_key
                and r.title == seed.title
            ),
            None,
        )
        if match is None:
            match = Role(
                company_id=company_id,
                title=seed.title,
                level=seed.level,
                description=seed.description,
                role_key=seed.role_key,
                is_active=seed.is_active,
            )
            session.add(match)
            existing_roles.append(match)
        else:
            match.level = seed.level
            match.description = seed.description
            match.is_active = seed.is_active
        by_natural_key[seed.natural_key] = match

    await session.flush()
    return by_natural_key


async def _upsert_templates(
    session: AsyncSession,
    seeds: list[_TemplateSeed],
    companies_by_slug: dict[str, Company],
    roles_by_natural_key: dict[str, Role],
) -> tuple[int, int]:
    result = await session.execute(select(InterviewTemplate))
    existing_templates = list(result.scalars().all())

    round_count = 0
    for seed in seeds:
        company = companies_by_slug[seed.company_slug] if seed.company_slug else None
        company_id = company.id if company else None
        role = roles_by_natural_key[seed.role_natural_key]

        template = next(
            (
                t
                for t in existing_templates
                if t.company_id == company_id and t.role_id == role.id and t.name == seed.name
            ),
            None,
        )
        if template is None:
            template = InterviewTemplate(
                company_id=company_id,
                role_id=role.id,
                name=seed.name,
                description=seed.description,
                default_difficulty=seed.default_difficulty,
                mode=seed.mode,
                is_active=seed.is_active,
            )
            session.add(template)
            await session.flush()
            existing_templates.append(template)
        else:
            template.description = seed.description
            template.default_difficulty = seed.default_difficulty
            template.mode = seed.mode
            template.is_active = seed.is_active
            await session.flush()

        round_count += await _upsert_rounds(session, template.id, seed.rounds)

    return len(seeds), round_count


async def _upsert_rounds(
    session: AsyncSession, template_id: uuid.UUID, seeds: list[_RoundSeed]
) -> int:
    result = await session.execute(
        select(TemplateRound).where(TemplateRound.template_id == template_id)
    )
    existing_by_seq = {r.sequence_no: r for r in result.scalars().all()}
    seed_sequence_numbers = {s.sequence_no for s in seeds}

    for seed in seeds:
        row = existing_by_seq.get(seed.sequence_no)
        if row is None:
            session.add(
                TemplateRound(
                    template_id=template_id,
                    round_type=seed.round_type,
                    sequence_no=seed.sequence_no,
                    weight=seed.weight,
                    is_required=seed.is_required,
                    difficulty_override=seed.difficulty_override,
                )
            )
        else:
            row.round_type = seed.round_type
            row.weight = seed.weight
            row.is_required = seed.is_required
            row.difficulty_override = seed.difficulty_override
    await session.flush()

    # Best-effort removal of rounds no longer present in catalog.json — never
    # fails the whole seed if a live interview_rounds row still references
    # one (ON DELETE RESTRICT), just skips and logs.
    for sequence_no, row in existing_by_seq.items():
        if sequence_no in seed_sequence_numbers:
            continue
        try:
            # A SAVEPOINT (not a bare rollback): an IntegrityError here must
            # only undo *this* delete, never the companies/roles/templates
            # already flushed earlier in the same seed transaction.
            async with session.begin_nested():
                await session.delete(row)
                await session.flush()
        except IntegrityError:
            logger.warning(
                "catalog.seed.round_delete_skipped",
                template_id=str(template_id),
                sequence_no=sequence_no,
                reason="referenced by an existing interview_rounds row",
            )

    return len(seeds)
