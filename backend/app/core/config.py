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

    # --- LLM provider (agents, Module 5+; Resume Intelligence, Module 3)
    GEMINI_API_KEY: str | None = None
    GEMINI_MODEL: str = "gemini-2.5-flash"
    GEMINI_EMBEDDING_MODEL: str = "text-embedding-004"

    # --- Pluggable backends (Architecture.md §6, §8.1) — config selects the
    # implementation, services depend only on the Protocol. "fake"
    # (Module 6) exists only so tests can exercise the coding-round flow
    # deterministically without a running `executor` container — same
    # rationale/production-guard as every other "fake" option below (see
    # app/execution/factories.py).
    CODE_EXECUTION_BACKEND: Literal["docker_sandbox", "judge0", "fake"] = "docker_sandbox"
    JOB_RUNNER_BACKEND: Literal["background_tasks", "celery"] = "background_tasks"

    # --- Resume Intelligence (Module 3) ---------------------------------
    # ResumeStorage backend (app/storage/) — "local" writes under
    # RESUME_STORAGE_LOCAL_DIR on the backend's own filesystem/volume.
    # An object-storage backend (Azure Blob/S3) is a second implementation
    # of the same Protocol, selected the same way CODE_EXECUTION_BACKEND is
    # — never a business-logic change.
    RESUME_STORAGE_BACKEND: Literal["local"] = "local"
    RESUME_STORAGE_LOCAL_DIR: str = "./data/resumes"
    RESUME_MAX_UPLOAD_MB: int = 5

    # ResumeIntelligenceProvider (app/services/resume_intelligence/) — the
    # LLM-backed structured-extraction seam. "fake" exists only so the
    # background job (app/jobs/resume_processing.py, which builds its own
    # provider instance and can't go through app.dependency_overrides) can
    # be driven deterministically in tests — see .env.test and
    # tests/conftest.py's autouse fake-provider-reset fixture. Mirrors
    # EMAIL_PROVIDER=console's shape: app/services/resume/factories.py
    # refuses to construct the fake in ENVIRONMENT=production, exactly
    # like ConsoleEmailProvider does, so a misconfigured deployment fails
    # loudly at startup instead of silently fabricating resume data.
    RESUME_INTELLIGENCE_PROVIDER: Literal["gemini", "fake"] = "gemini"
    RESUME_INTELLIGENCE_TIMEOUT_SECONDS: int = 45

    # EmbeddingProvider for resume_embeddings (ChromaDB, Database.md §9).
    # Same "fake" rationale as RESUME_INTELLIGENCE_PROVIDER above.
    RESUME_EMBEDDING_PROVIDER: Literal["gemini", "fake"] = "gemini"

    # --- Interview Engine (Module 5) -------------------------------------
    # InterviewAgentProvider (app/services/interview_intelligence/) — the
    # LLM-backed seam behind question generation, follow-ups, and
    # evaluation. Same "fake" rationale/production-guard as
    # RESUME_INTELLIGENCE_PROVIDER above (see
    # app/services/interview_intelligence/factories.py).
    INTERVIEW_ENGINE_PROVIDER: Literal["gemini", "fake"] = "gemini"
    INTERVIEW_ENGINE_TIMEOUT_SECONDS: int = 45

    # --- Code Execution Subsystem (Module 6) -----------------------------
    # DockerSandboxExecutor (app/execution/docker_sandbox.py) never talks to
    # Docker directly — it calls a dedicated sibling `executor` container
    # (backend/execution_worker/) over plain HTTP. That container has no
    # Docker socket, no project source, no application secrets, and sits on
    # a Compose network with `internal: true` (no route to the internet or
    # host) — see docker-compose.yml and docs/Architecture.md §6.
    EXECUTOR_BASE_URL: str = "http://executor:8100"
    CODE_EXECUTION_TIMEOUT_SECONDS: int = 10
    CODE_EXECUTION_MEMORY_LIMIT_MB: int = 256
    CODE_EXECUTION_MAX_OUTPUT_BYTES: int = 65536

    # CodeEvaluationProvider (app/services/code_evaluation/) — the LLM-backed
    # seam behind readability/optimization/edge-case judgment of a *final*
    # code submission only. correctness_score is never produced by this
    # provider — it's computed from code_submission_test_results before the
    # provider is ever called (module §10). Same "fake" rationale/
    # production-guard as INTERVIEW_ENGINE_PROVIDER above.
    CODE_EVALUATION_PROVIDER: Literal["gemini", "fake"] = "gemini"
    CODE_EVALUATION_TIMEOUT_SECONDS: int = 45


@lru_cache
def get_settings() -> Settings:
    """Cached settings instance — .env is read once per process, not per request."""
    return Settings()
