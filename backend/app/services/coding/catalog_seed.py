"""Module 6 — idempotent coding-problem catalog seeding. Mirrors
app/services/planning/catalog_seed.py's shape and idempotency approach
exactly (module §8: "a maintainable coding-problem catalog, not
hardcoded... prefer a small, high-quality catalog over hundreds of fake
problems"). The catalog lives in data/coding_problems.json; this module
only knows how to upsert it, so adding/editing a problem is a data
change, never a code change.

Idempotency strategy (safe to call on every app startup or from a
script, any number of times):
- Problems matched by their existing unique `slug`.
- Test cases matched by (problem_id, sequence_no) — the actual DB unique
  constraint. Unlike planning's template_rounds, no other table holds a
  live FK to coding_problem_test_cases (confirmed: only the
  CodingProblem.test_cases relationship references it — a problem is
  SNAPSHOTTED into Question/QuestionTestCase rows at selection time, see
  app/models/coding.py's module docstring), so there is no ON DELETE
  RESTRICT hazard here and no need for planning's SAVEPOINT-guarded
  delete-skip dance: test cases removed from the JSON are simply deleted.
"""

import json
import uuid
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.coding import CodingProblem, CodingProblemTestCase
from app.models.enums import DifficultyLevel

logger = get_logger(__name__)

_CATALOG_PATH = Path(__file__).parent / "data" / "coding_problems.json"


class _TestCaseSeed(BaseModel):
    input: str
    expected_output: str
    is_sample: bool = False
    sequence_no: int


class _ProblemSeed(BaseModel):
    slug: str
    title: str
    description: str
    difficulty: DifficultyLevel
    topics: list[str] = Field(default_factory=list)
    constraints: str | None = None
    expected_time_complexity: str | None = None
    expected_space_complexity: str | None = None
    supported_languages: list[str] = Field(default_factory=list)
    starter_code: dict[str, str] = Field(default_factory=dict)
    role_keys: list[str] = Field(default_factory=list)
    is_active: bool = True
    test_cases: list[_TestCaseSeed]


class _CodingCatalogSeed(BaseModel):
    problems: list[_ProblemSeed]


@lru_cache
def _load_catalog() -> _CodingCatalogSeed:
    raw = json.loads(_CATALOG_PATH.read_text(encoding="utf-8"))
    raw.pop("_comment", None)
    return _CodingCatalogSeed.model_validate(raw)


async def seed_coding_catalog(session: AsyncSession) -> dict[str, int]:
    """Upserts every problem/test case in data/coding_problems.json.
    Returns a small summary dict for logging/CLI output. Commits once at
    the end — the whole catalog seeds atomically, or not at all.
    """
    catalog = _load_catalog()
    counts = {"problems": 0, "test_cases": 0}

    result = await session.execute(select(CodingProblem))
    existing = {p.slug: p for p in result.scalars().all()}

    test_case_count = 0
    for seed in catalog.problems:
        problem = existing.get(seed.slug)
        if problem is None:
            problem = CodingProblem(
                slug=seed.slug,
                title=seed.title,
                description=seed.description,
                difficulty=seed.difficulty,
                topics=seed.topics,
                constraints=seed.constraints,
                expected_time_complexity=seed.expected_time_complexity,
                expected_space_complexity=seed.expected_space_complexity,
                supported_languages=seed.supported_languages,
                starter_code=seed.starter_code,
                role_keys=seed.role_keys,
                is_active=seed.is_active,
            )
            session.add(problem)
            await session.flush()
        else:
            problem.title = seed.title
            problem.description = seed.description
            problem.difficulty = seed.difficulty
            problem.topics = seed.topics
            problem.constraints = seed.constraints
            problem.expected_time_complexity = seed.expected_time_complexity
            problem.expected_space_complexity = seed.expected_space_complexity
            problem.supported_languages = seed.supported_languages
            problem.starter_code = seed.starter_code
            problem.role_keys = seed.role_keys
            problem.is_active = seed.is_active

        test_case_count += await _upsert_test_cases(session, problem.id, seed.test_cases)

    await session.commit()
    counts["problems"] = len(catalog.problems)
    counts["test_cases"] = test_case_count
    logger.info("coding_catalog.seeded", **counts)
    return counts


async def _upsert_test_cases(
    session: AsyncSession, problem_id: uuid.UUID, seeds: list[_TestCaseSeed]
) -> int:
    # Explicit query, not a `problem.test_cases` relationship access —
    # the latter would attempt an implicit lazy-load on a just-flushed
    # object, which raises MissingGreenlet under the async driver (mirrors
    # planning/catalog_seed.py's _upsert_rounds, which avoids the same
    # trap the same way).
    result = await session.execute(
        select(CodingProblemTestCase).where(CodingProblemTestCase.problem_id == problem_id)
    )
    existing_by_seq = {tc.sequence_no: tc for tc in result.scalars().all()}
    seed_sequence_numbers = {s.sequence_no for s in seeds}

    for seed in seeds:
        row = existing_by_seq.get(seed.sequence_no)
        if row is None:
            session.add(
                CodingProblemTestCase(
                    problem_id=problem_id,
                    input=seed.input,
                    expected_output=seed.expected_output,
                    is_sample=seed.is_sample,
                    sequence_no=seed.sequence_no,
                )
            )
        else:
            row.input = seed.input
            row.expected_output = seed.expected_output
            row.is_sample = seed.is_sample

    # No ON DELETE RESTRICT hazard here (see module docstring) — test
    # cases dropped from the JSON are simply removed.
    for sequence_no, row in existing_by_seq.items():
        if sequence_no not in seed_sequence_numbers:
            await session.delete(row)

    await session.flush()
    return len(seeds)
