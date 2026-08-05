"""Shared FastAPI dependencies.

Routers depend on these, never on concrete infra (engines, clients,
backend implementations) directly — this is the seam that makes backends
swappable via config (Architecture.md §6, §8.1) and makes services
testable by overriding a dependency instead of monkeypatching an import.
"""

from collections.abc import Callable
from typing import Annotated

from fastapi import BackgroundTasks, Depends, Header
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache.redis_client import get_redis
from app.core.config import Settings, get_settings
from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.core.security import InvalidTokenError, TokenType, decode_token
from app.db.session import get_db_session
from app.execution.base import CodeExecutor
from app.execution.docker_sandbox import DockerSandboxExecutor
from app.jobs.background_tasks_runner import BackgroundTasksRunner
from app.jobs.base import JobRunner
from app.models.enums import UserRole
from app.models.user import User
from app.services.auth_service import AuthService
from app.services.email import ConsoleEmailProvider, EmailProvider
from app.services.oauth import GoogleOAuthProvider
from app.services.resume.factories import build_embedding_index, build_resume_storage
from app.services.resume.resume_service import ResumeService
from app.storage.base import ResumeStorage
from app.vectorstore.resume_embeddings import ResumeEmbeddingIndex

DbSession = Annotated[AsyncSession, Depends(get_db_session)]
RedisClient = Annotated[Redis, Depends(get_redis)]
AppSettings = Annotated[Settings, Depends(get_settings)]


def get_job_runner(background_tasks: BackgroundTasks, settings: AppSettings) -> JobRunner:
    if settings.JOB_RUNNER_BACKEND == "background_tasks":
        return BackgroundTasksRunner(background_tasks)
    raise NotImplementedError(f"job runner backend {settings.JOB_RUNNER_BACKEND!r} not wired yet")


JobRunnerDep = Annotated[JobRunner, Depends(get_job_runner)]


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
    """Validates a bearer access token and loads the User row. Registration,
    login, and refresh-rotation logic live in AuthService — this dependency
    only ever reads an already-issued access token.
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


def require_role(*allowed_roles: UserRole) -> Callable[[CurrentUser], User]:
    """Role-authorization dependency factory.

    Distinct from get_current_user (401 unauthenticated: missing/invalid
    token) — this raises 403 forbidden for an authenticated user whose
    role isn't in `allowed_roles`. Usage:

        @router.get("/admin/...")
        async def admin_only(user: Annotated[User, Depends(require_role(UserRole.ADMIN))]): ...
    """

    def _check(user: CurrentUser) -> User:
        if user.role not in allowed_roles:
            raise ForbiddenError("you do not have permission to perform this action")
        return user

    return _check


def get_email_provider(settings: AppSettings) -> EmailProvider:
    if settings.EMAIL_PROVIDER == "console":
        return ConsoleEmailProvider(settings)
    raise NotImplementedError(f"email provider {settings.EMAIL_PROVIDER!r} not wired yet")


def get_google_oauth_provider(settings: AppSettings) -> GoogleOAuthProvider:
    return GoogleOAuthProvider(settings)


def get_auth_service(session: DbSession, settings: AppSettings) -> AuthService:
    return AuthService(session, settings)


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]
EmailProviderDep = Annotated[EmailProvider, Depends(get_email_provider)]
GoogleOAuthProviderDep = Annotated[GoogleOAuthProvider, Depends(get_google_oauth_provider)]


def get_resume_storage(settings: AppSettings) -> ResumeStorage:
    return build_resume_storage(settings)


def get_resume_embedding_index(settings: AppSettings) -> ResumeEmbeddingIndex:
    return build_embedding_index(settings)


ResumeStorageDep = Annotated[ResumeStorage, Depends(get_resume_storage)]
ResumeEmbeddingIndexDep = Annotated[ResumeEmbeddingIndex, Depends(get_resume_embedding_index)]


def get_resume_service(
    session: DbSession, settings: AppSettings, storage: ResumeStorageDep
) -> ResumeService:
    # embedding_index is passed as a *factory*, not a resolved instance —
    # FastAPI resolves every Depends() in a route's dependency tree before
    # the endpoint body runs, so making ResumeEmbeddingIndexDep a direct
    # parameter here would construct GeminiEmbeddingProvider (which raises
    # if GEMINI_API_KEY is unset) on every resume request, including
    # upload/list/get — none of which touch embeddings at all. Only
    # ResumeService.delete_resume's already-best-effort cleanup calls this,
    # so construction failure there is just one more thing that path logs
    # and swallows, per module §9 ("the endpoint must not become useless
    # if Gemini is temporarily unavailable"). Caught the eager-construction
    # version of this during Docker verification, not by inspection — see
    # backend/README.md's "What was actually verified" section.
    return ResumeService(session, settings, storage, lambda: build_embedding_index(settings))


ResumeServiceDep = Annotated[ResumeService, Depends(get_resume_service)]


async def db_healthcheck(session: DbSession) -> bool:
    from sqlalchemy import text

    await session.execute(text("SELECT 1"))
    return True


async def redis_healthcheck(redis: RedisClient) -> bool:
    return await redis.ping()
