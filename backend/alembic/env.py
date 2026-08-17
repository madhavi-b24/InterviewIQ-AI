import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.core.config import get_settings
from app.models import Base  # noqa: F401 — importing registers all tables on Base.metadata

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Single source of truth for the connection string: app.core.config, not
# alembic.ini, so migrations always run against the same DB the app uses.
config.set_main_option("sqlalchemy.url", get_settings().DATABASE_URL)

target_metadata = Base.metadata

# Module 5 — LangGraph's own checkpoint tables (app/agents/checkpointer.py,
# created by AsyncPostgresSaver.setup(), not by us) live in this same
# Postgres database but are a separate, library-owned schema — never part
# of Base.metadata. Without this filter, `alembic check`/`--autogenerate`
# sees them as "extra tables not in our metadata" and proposes DROP TABLE
# migrations for infrastructure we don't own and must never touch. Found
# by actually running `alembic check` after these tables existed, not by
# inspection — see backend/README.md's Module 5 verification notes.
_LANGGRAPH_CHECKPOINT_TABLES = {
    "checkpoints",
    "checkpoint_blobs",
    "checkpoint_writes",
    "checkpoint_migrations",
}


def _include_object(object_, name, type_, reflected, compare_to):
    return not (type_ == "table" and name in _LANGGRAPH_CHECKPOINT_TABLES)


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=_include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def _do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection, target_metadata=target_metadata, include_object=_include_object
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        future=True,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(_do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
