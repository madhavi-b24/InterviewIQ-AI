"""CLI entrypoint for seeding the Module 4 interview-planning catalog —
Roadmap.md's Module 4 scope: "companies/roles/interview_templates/
template_rounds seeded via script (no admin UI yet)".

Usage:
    uv run python -m app.db.seed_catalog

Safe to run repeatedly (idempotent upsert — see
app/services/planning/catalog_seed.py). Also invoked automatically by
tests via a session-scoped fixture (tests/conftest.py) since it only
mutates catalog tables the per-test cleanup fixture never truncates.
"""

import asyncio

from app.core.logging import configure_logging, get_logger
from app.db.session import get_session_factory
from app.services.planning.catalog_seed import seed_catalog

logger = get_logger(__name__)


async def main() -> None:
    configure_logging()
    session_factory = get_session_factory()
    async with session_factory() as session:
        counts = await seed_catalog(session)
    logger.info("catalog.seed.cli_complete", **counts)
    print(f"Catalog seeded: {counts}")


if __name__ == "__main__":
    asyncio.run(main())
