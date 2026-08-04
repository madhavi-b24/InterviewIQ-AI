from functools import lru_cache
from typing import Literal

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
    CORS_ORIGINS: list[str] = ["http://localhost:5173"]

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

    # --- Google OAuth (Module 2)
    GOOGLE_CLIENT_ID: str | None = None
    GOOGLE_CLIENT_SECRET: str | None = None

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
