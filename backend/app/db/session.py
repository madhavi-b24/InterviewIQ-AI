"""Async engine + session factory.

One engine per process, created lazily and cached — see get_engine().
Routes never import the engine directly; they depend on get_db_session,
wired in app/api/deps.py, so tests can override it with a different engine.
"""

from collections.abc import AsyncGenerator
from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings


@lru_cache
def get_engine() -> AsyncEngine:
    settings = get_settings()
    return create_async_engine(settings.DATABASE_URL, pool_pre_ping=True, future=True)


@lru_cache
def get_session_factory() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(bind=get_engine(), expire_on_commit=False, autoflush=False)


async def get_db_session() -> AsyncGenerator[AsyncSession]:
    session_factory = get_session_factory()
    async with session_factory() as session:
        yield session
