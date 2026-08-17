"""LangGraph checkpointer wiring — Architecture.md §5.5.

This is infra (connecting LangGraph's persistence to our Postgres), not
agent logic, so it's safe to wire now even though no graph exists yet.
`AsyncPostgresSaver.setup()` creates LangGraph's own checkpoint tables the
first time it runs — separate from and unrelated to our Alembic-managed
schema in Database.md.

**Windows dev-only fix, found by actually running this code, not by
inspection**: `AsyncPostgresSaver` uses `psycopg`'s async mode, which
refuses to run under Python's default Windows event loop
(`ProactorEventLoop`) — `psycopg.InterfaceError: Psycopg cannot use the
'ProactorEventLoop' to run in async mode`. This was dormant scaffold code
(module §0's "checkpointer.py is real, working infra") that had never
actually been exercised before Module 5 first called `get_checkpointer()`
for real. `SelectorEventLoop` (Python's other built-in Windows loop) is
fully compatible and has no impact on anything this app actually does with
asyncio (its one limitation — no `asyncio.create_subprocess_*` support —
isn't used anywhere in this codebase). Guarded by `sys.platform`, so this
is a no-op on Linux/the Docker deployment target, which was never affected
(the default event loop there always worked fine with psycopg async).
"""

import asyncio
import sys
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from app.core.config import get_settings

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def _psycopg_conninfo() -> str:
    # AsyncPostgresSaver uses psycopg (not asyncpg), so translate the
    # SQLAlchemy-style URL into a plain libpq connection string.
    settings = get_settings()
    return settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")


@asynccontextmanager
async def get_checkpointer() -> AsyncGenerator[AsyncPostgresSaver]:
    async with AsyncPostgresSaver.from_conn_string(_psycopg_conninfo()) as checkpointer:
        yield checkpointer
