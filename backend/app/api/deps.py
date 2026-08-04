"""Shared FastAPI dependencies.

Routers depend on these, never on concrete infra (engines, clients,
backend implementations) directly — this is the seam that makes backends
swappable via config (Architecture.md §6, §8.1) and makes services
testable by overriding a dependency instead of monkeypatching an import.
"""

from typing import Annotated

from fastapi import BackgroundTasks, Depends, Header
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache.redis_client import get_redis
from app.core.config import Settings, get_settings
from app.core.exceptions import UnauthorizedError
from app.core.security import InvalidTokenError, TokenType, decode_token
from app.db.session import get_db_session
from app.execution.base import CodeExecutor
from app.execution.docker_sandbox import DockerSandboxExecutor
from app.jobs.background_tasks_runner import BackgroundTasksRunner
from app.jobs.base import JobRunner
from app.models.user import User

DbSession = Annotated[AsyncSession, Depends(get_db_session)]
RedisClient = Annotated[Redis, Depends(get_redis)]
AppSettings = Annotated[Settings, Depends(get_settings)]


def get_job_runner(background_tasks: BackgroundTasks, settings: AppSettings) -> JobRunner:
    if settings.JOB_RUNNER_BACKEND == "background_tasks":
        return BackgroundTasksRunner(background_tasks)
    raise NotImplementedError(f"job runner backend {settings.JOB_RUNNER_BACKEND!r} not wired yet")


def get_code_executor(settings: AppSettings) -> CodeExecutor:
    if settings.CODE_EXECUTION_BACKEND == "docker_sandbox":
        return DockerSandboxExecutor()
    raise NotImplementedError(
        f"code execution backend {settings.CODE_EXECUTION_BACKEND!r} not wired yet"
    )


async def _bearer_token(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise UnauthorizedError("missing or malformed Authorization header")
    return authorization.split(" ", 1)[1]


async def get_current_user(
    session: DbSession,
    authorization: Annotated[str | None, Header()] = None,
) -> User:
    """Placeholder auth dependency: validates a bearer access token and
    loads the User row. Endpoint-level concerns (registration, login,
    refresh rotation) belong to Module 2's AuthService, not here.
    """
    token = await _bearer_token(authorization)
    try:
        user_id = decode_token(token, TokenType.ACCESS)
    except InvalidTokenError as exc:
        raise UnauthorizedError("invalid or expired access token") from exc

    user = await session.get(User, user_id)
    if user is None or not user.is_active:
        raise UnauthorizedError("user not found or inactive")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def db_healthcheck(session: DbSession) -> bool:
    from sqlalchemy import text

    await session.execute(text("SELECT 1"))
    return True


async def redis_healthcheck(redis: RedisClient) -> bool:
    return await redis.ping()
