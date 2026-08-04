"""Liveness/readiness endpoint — the one real endpoint in this scaffold.

GET /health checks Postgres and Redis connectivity so `docker-compose up`
can prove the stack is actually wired, not just that FastAPI started.
"""

from fastapi import APIRouter

from app.api.deps import DbSession, RedisClient, db_healthcheck, redis_healthcheck

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(session: DbSession, redis: RedisClient) -> dict:
    checks = {
        "database": await _safe(db_healthcheck, session),
        "redis": await _safe(redis_healthcheck, redis),
    }
    return {"status": "ok" if all(checks.values()) else "degraded", "checks": checks}


async def _safe(check_fn, dependency) -> bool:
    try:
        return await check_fn(dependency)
    except Exception:  # noqa: BLE001 — a health check must never raise, only report
        return False
