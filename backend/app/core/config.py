from functools import lru_cache
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-driven configuration. Every field maps to one env var.

    Never import os.environ directly elsewhere in the app — go through
    get_settings() so there is exactly one place that knows how config
    is sourced.
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- App
    ENVIRONMENT: Literal["local", "test", "staging", "production"] = "local"
    LOG_LEVEL: str = "INFO"
    API_V1_PREFIX: str = "/api/v1"
    # http://localhost:5173 is Vite's default dev port — the future React
    # frontend. app.main.create_app() always sets allow_credentials=True
    # on CORSMiddleware, and the Fetch/CORS spec forbids browsers from
    # honoring "Access-Control-Allow-Origin: *" together with
    # "Access-Control-Allow-Credentials: true" — Starlette will not stop
    # you from configuring that combination, so it's rejected here instead
    # of being discovered later as a silently-broken (or, on older/buggy
    # clients, unsafely-permissive) CORS setup.
    CORS_ORIGINS: list[str] = ["http://localhost:5173"]

    @field_validator("CORS_ORIGINS")
    @classmethod
    def cors_origins_must_not_be_wildcard(cls, value: list[str]) -> list[str]:
        if "*" in value:
            raise ValueError(
                "CORS_ORIGINS must not contain '*' — this app always sends "
                "Access-Control-Allow-Credentials: true, and browsers reject "
                "that combined with a wildcard origin. List explicit origins."
            )
        return value

    # --- Database (SQLAlchemy 2.0 async, asyncpg driver)
    DATABASE_URL: str = "postgresql+asyncpg://interviewiq:interviewiq@localhost:5432/interviewiq"

    # --- Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # --- ChromaDB
    CHROMA_HOST: str = "localhost"
    CHROMA_PORT: int = 8001

    # --- JWT auth (see Architecture.md §8.2)
    JWT_SECRET_KEY: str = "change-me-in-.env"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # --- Password reset (Module 2)
    PASSWORD_RESET_TOKEN_EXPIRE_MINUTES: int = 30

    # --- Email delivery (Module 2). "console" logs the reset link instead of
    # sending real email — the only mock allowed in non-production, see
    # app/services/email.py. There is no production provider wired up yet;
    # ENVIRONMENT=production with EMAIL_PROVIDER=console fails fast on send
    # rather than silently faking delivery.
    EMAIL_PROVIDER: Literal["console"] = "console"

    # --- Google OAuth (Module 2). Unset in local/dev by default — the
    # provider abstraction (app/services/oauth.py) works either way;
    # GET /auth/google/login returns 503 OAUTH_NOT_CONFIGURED until these
    # and GOOGLE_REDIRECT_URI are set.
    GOOGLE_CLIENT_ID: str | None = None
    GOOGLE_CLIENT_SECRET: str | None = None
    GOOGLE_REDIRECT_URI: str | None = None

    # --- LLM provider (agents, Module 5+)
    GEMINI_API_KEY: str | None = None

    # --- Pluggable backends (Architecture.md §6, §8.1) — config selects the
    # implementation, services depend only on the Protocol.
    CODE_EXECUTION_BACKEND: Literal["docker_sandbox", "judge0"] = "docker_sandbox"
    JOB_RUNNER_BACKEND: Literal["background_tasks", "celery"] = "background_tasks"


@lru_cache
def get_settings() -> Settings:
    """Cached settings instance — .env is read once per process, not per request."""
    return Settings()
