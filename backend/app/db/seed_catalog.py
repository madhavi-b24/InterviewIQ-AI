"""CLI entrypoint for seeding every MVP catalog — Module 4's interview-
planning catalog ("companies/roles/interview_templates/template_rounds
seeded via script, no admin UI yet", Roadmap.md) plus Module 6's coding-
problem catalog (same rationale — module §8's "maintainable catalog, not
hardcoded").

Usage:
    uv run python -m app.db.seed_catalog

Safe to run repeatedly (idempotent upsert — see
app/services/planning/catalog_seed.py and app/services/coding/catalog_seed.py).
Also invoked automatically by tests via autouse fixtures (tests/conftest.py)
since both only mutate catalog tables the per-test cleanup fixture never
truncates.
"""

import asyncio

from app.core.logging import configure_logging, get_logger
from app.db.session import get_session_factory
from app.services.coding.catalog_seed import seed_coding_catalog
from app.services.planning.catalog_seed import seed_catalog

logger = get_logger(__name__)


async def main() -> None:
    configure_logging()
    session_factory = get_session_factory()
    async with session_factory() as session:
        counts = await seed_catalog(session)
    logger.info("catalog.seed.cli_complete", **counts)
    print(f"Interview catalog seeded: {counts}")

    async with session_factory() as session:
        coding_counts = await seed_coding_catalog(session)
    logger.info("coding_catalog.seed.cli_complete", **coding_counts)
    print(f"Coding catalog seeded: {coding_counts}")


if __name__ == "__main__":
    asyncio.run(main())
