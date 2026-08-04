"""Async Redis client, one connection pool per process.

Per Architecture.md §5.5: Redis is a cache, never the source of truth.
Anything stored here (session hot-state, submission status, rate limits)
must be reconstructable from Postgres if this is flushed.
"""

from collections.abc import AsyncGenerator
from functools import lru_cache

from redis.asyncio import ConnectionPool, Redis

from app.core.config import get_settings


@lru_cache
def get_redis_pool() -> ConnectionPool:
    settings = get_settings()
    return ConnectionPool.from_url(settings.REDIS_URL, decode_responses=True)


async def get_redis() -> AsyncGenerator[Redis]:
    client = Redis(connection_pool=get_redis_pool())
    try:
        yield client
    finally:
        await client.aclose()
