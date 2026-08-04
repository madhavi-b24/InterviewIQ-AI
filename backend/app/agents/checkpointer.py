"""LangGraph checkpointer wiring — Architecture.md §5.5.

This is infra (connecting LangGraph's persistence to our Postgres), not
agent logic, so it's safe to wire now even though no graph exists yet.
`AsyncPostgresSaver.setup()` creates LangGraph's own checkpoint tables the
first time it runs — separate from and unrelated to our Alembic-managed
schema in Database.md.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from app.core.config import get_settings


def _psycopg_conninfo() -> str:
    # AsyncPostgresSaver uses psycopg (not asyncpg), so translate the
    # SQLAlchemy-style URL into a plain libpq connection string.
    settings = get_settings()
    return settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")


@asynccontextmanager
async def get_checkpointer() -> AsyncGenerator[AsyncPostgresSaver]:
    async with AsyncPostgresSaver.from_conn_string(_psycopg_conninfo()) as checkpointer:
        yield checkpointer
