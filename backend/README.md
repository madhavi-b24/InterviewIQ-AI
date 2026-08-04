# InterviewIQ AI — Backend

FastAPI backend for InterviewIQ AI. This is the **Module 1 scaffold**: architecture, database schema, and infrastructure wiring only — no feature logic yet. See [../docs/Roadmap.md](../docs/Roadmap.md) for what comes next, and [../docs/Architecture.md](../docs/Architecture.md) / [../docs/Database.md](../docs/Database.md) for the design this scaffold implements.

## Stack

FastAPI · Python 3.12 · [uv](https://docs.astral.sh/uv/) · PostgreSQL + SQLAlchemy 2.0 (async) · Alembic · Redis · ChromaDB (client) · LangGraph · Ruff + Black · pytest

**Why uv instead of Poetry:** the task allowed either, with a recommendation to justify. uv is used here because it's a single tool for dependency resolution, virtualenv management, and Python version pinning (`.python-version`) instead of three; it resolves and installs an order of magnitude faster, which matters most during CI and Docker builds; its lockfile (`uv.lock`) is deterministic across platforms; and it uses standard PEP 621 `[project]` metadata in `pyproject.toml` rather than Poetry's own `[tool.poetry]` dialect, so the file stays portable if we ever move tooling again. It's also made by Astral, the same team behind Ruff, which this project already uses.

## Setup

```bash
cd backend
uv sync                        # creates .venv, installs everything from uv.lock
cp .env.example .env           # edit if your local Postgres/Redis differ from the defaults
```

Bring up Postgres + Redis (from the repo root):

```bash
docker compose up -d postgres redis
```

Apply migrations and run the app:

```bash
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

`GET http://localhost:8000/api/v1/health` should return `{"status": "ok", "checks": {"database": true, "redis": true}}`.

### Tests, lint, format

```bash
uv run pytest              # needs an `interviewiq_test` Postgres DB — see docker-compose.yml's postgres-init script
uv run ruff check .        # linting + import sorting
uv run black .             # formatting
```

### Docker

```bash
docker compose up -d       # from the repo root: postgres, redis, chromadb, backend
```

The backend's Dockerfile is a two-stage build (uv-based builder → slim runtime, non-root user). This has been built and run end-to-end against the full compose stack as part of this scaffold's verification.

### Everyday commands

| Task | Command |
|---|---|
| Add a dependency | `uv add <package>` |
| Add a dev-only dependency | `uv add --group dev <package>` |
| New migration after changing models | `uv run alembic revision --autogenerate -m "..."` |
| Run one test file | `uv run pytest tests/test_health.py` |

---

## What's here, and why

### Root files

| File | Purpose |
|---|---|
| `pyproject.toml` | Single source of truth for dependencies (`[project.dependencies]`, `[dependency-groups.dev]`), and tool config for Ruff, Black, and pytest. `hatchling` is the build backend — lightweight, PEP 621-native, no reason to reach for setuptools. |
| `.python-version` | Pins Python 3.12 for uv (`uv python install/pin` reads this). |
| `.env.example` | Every setting `app/core/config.py` reads, documented, with safe local defaults. Copy to `.env`; never commit the real `.env`. |
| `.env` / `.env.test` | Local dev / test-suite environment files — gitignored. `.env.test` points at a separate `interviewiq_test` database and `redis` DB index so the test suite never touches dev data. |
| `.dockerignore` | Keeps the build context small and secrets (`.env`) out of the image. `README.md` is deliberately **not** ignored — `pyproject.toml`'s `readme` field requires it to exist at build time. |
| `Dockerfile` | Multi-stage: a `builder` stage resolves deps with uv into `.venv`, a `runtime` stage copies only `.venv` + `app/` + `alembic/` into a slim image running as a non-root user. Dependencies are installed before `COPY . .` so that layer only invalidates when `pyproject.toml`/`uv.lock` actually change. |
| `alembic.ini` | Alembic's own config. Deliberately has **no** `sqlalchemy.url` — `alembic/env.py` sources the connection string from `app.core.config.get_settings()` so there is exactly one place the DB URL comes from, shared with the running app. |

### `app/core/` — infrastructure that isn't specific to any feature

| File | Purpose |
|---|---|
| `config.py` | `Settings` (Pydantic Settings), reading every env var once. `CODE_EXECUTION_BACKEND` and `JOB_RUNNER_BACKEND` are the config knobs that select pluggable implementations per Architecture.md §6/§8.1 — services depend on the Protocol, config decides which concrete class they get. |
| `logging.py` | structlog setup: pretty console output locally, structured JSON in staging/production, called once from `main.py`'s lifespan. |
| `security.py` | JWT creation/verification (`create_access_token`, `create_refresh_token`, `decode_token`) and password hashing (`hash_password`/`verify_password`). This is the "JWT authentication structure" the task asked for — it does **not** implement register/login endpoints; that's Module 2. |
| `exceptions.py` | `AppError` and subclasses (`NotFoundError`, `ConflictError`, `UnauthorizedError`, `ForbiddenError`) plus the FastAPI exception handlers that turn them into the `{"error": {...}}` envelope defined in API.md §0. |

### `app/db/`, `app/cache/`, `app/vectorstore/` — datastore connections

| File | Purpose |
|---|---|
| `db/base.py` | `Base` (SQLAlchemy declarative base) and two mixins — `UUIDPrimaryKeyMixin`, `TimestampMixin` — that encode Database.md §0's conventions (UUID PKs, `created_at`/`updated_at`) once instead of repeating them in 29 model classes. |
| `db/session.py` | Async engine + session factory (`get_db_session`), cached per-process. Routes never import the engine directly — always through this, so tests can override the dependency. |
| `cache/redis_client.py` | Async Redis connection pool + `get_redis` dependency. |
| `vectorstore/client.py` | ChromaDB `HttpClient` wrapper — connection only, no collections yet. We depend on the `chromadb-client` package (thin HTTP client) rather than full `chromadb`, since we always talk to the separate ChromaDB container and never embed it in-process; this also sidesteps `chromadb`'s native `hnswlib` dependency, which needs a C++ toolchain to build from source. |

### `app/models/` — SQLAlchemy ORM, one-to-one with Database.md

Every table in Database.md §2–§8 has a corresponding model. Split by domain, matching the doc's section structure:

| File | Tables |
|---|---|
| `enums.py` | Every Postgres ENUM as a Python `StrEnum`, plus `pg_enum()` — a helper that makes SQLAlchemy store each enum's lowercase `.value` (`"local"`, `"google"`) as the DB label. **Without this, SQLAlchemy defaults to storing the Python member's `.name`** (`"LOCAL"`, `"GOOGLE"`) instead, which would silently diverge from what Database.md documents. Caught this during verification, not by inspection — see below. |
| `user.py` | `users`, `refresh_tokens` |
| `resume.py` | `resumes`, `resume_skills`, `resume_projects`, `resume_experience`, `resume_gap_analysis` |
| `planning.py` | `companies`, `roles`, `interview_templates`, `template_rounds` |
| `interview.py` | `interview_sessions`, `interview_rounds`, `questions`, `question_test_cases`, `answers`, `code_submissions`, `code_submission_test_results` |
| `evaluation.py` | `answer_evaluations`, `coding_evaluations` |
| `report.py` | `interview_reports`, `report_section_scores`, `report_weak_areas`, `report_strong_areas`, `learning_roadmaps`, `roadmap_items` |
| `progress.py` | `skill_progress`, `company_readiness`, `user_progress_snapshots` |
| `__init__.py` | Imports every model module so `Base.metadata` is fully populated and cross-file string relationships (e.g. `relationship("Role")`) resolve. Alembic's `env.py` imports *this* package, not individual model files. |

### `app/repositories/`, `app/services/` — application layers (mostly empty by design)

| File | Purpose |
|---|---|
| `repositories/base.py` | Generic `BaseRepository[ModelT]` (get by id, add, list all) — the one piece of the repository pattern that's truly generic. Concrete repositories (`UserRepository`, etc.) are added starting with the module that first needs a feature-specific query; adding empty subclasses now would be exactly the "half-finished implementation" the project's own ground rules say to avoid. |
| `services/` | Empty package (just `__init__.py`). Use cases (`StartInterviewSession`, `AnalyzeResume`, ...) land here starting Module 2 — there's no generic "base service" pattern to scaffold ahead of the first real one. |

### `app/jobs/`, `app/execution/` — the two pluggable-backend seams

Both follow the same shape: a `Protocol` + config-selected implementation, per Architecture.md §6/§8.1.

| File | Purpose |
|---|---|
| `jobs/base.py` | `JobRunner` protocol (`enqueue(job_name, payload) -> job_id`). |
| `jobs/background_tasks_runner.py` | MVP implementation, wrapping FastAPI's `BackgroundTasks`. `JOB_HANDLERS` is an empty registry — first entry lands with Module 3's resume-parsing job. Swapping to Celery later means writing `CeleryRunner` and flipping `JOB_RUNNER_BACKEND`, not touching any caller. |
| `execution/base.py` | `CodeExecutor` protocol + `TestCase`/`TestCaseResult` dataclasses. |
| `execution/docker_sandbox.py` | `DockerSandboxExecutor` — the MVP backend selected by `CODE_EXECUTION_BACKEND=docker_sandbox`. Its `run()` raises `NotImplementedError`; real sandboxing (network isolation, resource limits) is Module 6, not this scaffold. |

### `app/agents/` — LangGraph wiring, no agents yet

| File | Purpose |
|---|---|
| `state.py` | `InterviewState` TypedDict — the shared graph state shape from Architecture.md §5.2. Field shapes only. |
| `checkpointer.py` | `get_checkpointer()` — wires LangGraph's `AsyncPostgresSaver` to our `DATABASE_URL` (translated to a psycopg-style conninfo string, since the checkpointer uses `psycopg`, not `asyncpg`). This is real, working infra: connecting persistence to Postgres, not agent behavior. |
| `graph.py` | `build_interview_graph()` — stub, raises `NotImplementedError`. The Supervisor and the eight other agents from Architecture.md §5.1 are Module 5 work. |

### `app/api/` — HTTP layer

| File | Purpose |
|---|---|
| `deps.py` | Every shared FastAPI dependency: `DbSession`, `RedisClient`, `get_current_user` (decodes a bearer JWT, loads the `User` row — auth *plumbing*, not the register/login feature), `get_job_runner`/`get_code_executor` (config-driven backend selection), and `db_healthcheck`/`redis_healthcheck`. |
| `v1/health.py` | `GET /health` — the one real endpoint in this scaffold. Actually pings Postgres and Redis rather than just returning 200, so `docker compose up` proves the stack is wired, not just that FastAPI started. |
| `v1/router.py` | Aggregates `v1` routers. Feature routers (`auth.py`, `resumes.py`, ...) get added here module by module. |

### `app/main.py`

`create_app()`: FastAPI instance, CORS middleware from `settings.CORS_ORIGINS`, exception handlers registered, `v1` router mounted at `/api/v1`. `lifespan()` configures logging on startup and disposes the DB engine on shutdown.

### `alembic/`

| File | Purpose |
|---|---|
| `env.py` | Async-compatible (`asyncio.run(run_migrations_online())`), imports `app.models.Base` for autogenerate, sources the DB URL from `app.core.config` rather than duplicating it in `alembic.ini`. |
| `script.py.mako` | Template for new migration files — stock Alembic template, included explicitly rather than left to `alembic init` defaults. |
| `versions/..._initial_schema.py` | The baseline migration, autogenerated from every model in `app/models/` and verified against a real Postgres instance (see below) — creates all 29 tables. |

### `tests/`

| File | Purpose |
|---|---|
| `conftest.py` | Loads `.env.test` *before* anything imports `app.core.config` (import order matters here — see the `noqa: E402`s), then provides an `httpx.AsyncClient` fixture wired to the app via `ASGITransport` (no real HTTP server needed for tests). |
| `test_health.py` | Exercises `GET /health` against real Postgres + Redis (the `.env.test` instances) — a smoke test that the whole scaffold, not just the app object, actually works. |

---

## What was actually verified, not just written

Every piece of this scaffold was run, not just authored:

- `uv sync` installs cleanly (143 packages resolved).
- `alembic revision --autogenerate` correctly detects all 29 tables from the models against a live Postgres instance, including the `code_submissions` partial unique index (`WHERE is_final`).
- **Found and fixed during verification, not by inspection:** two real bugs.
  1. SQLAlchemy's default `Enum` behavior stores the Python enum member's `.name` (`"LOCAL"`) rather than `.value` (`"local"`) — silently inconsistent with Database.md's documented lowercase values. Fixed with the `pg_enum()` helper in `app/models/enums.py`.
  2. Alembic's autogenerated `downgrade()` drops tables but not the Postgres ENUM *types* those tables used (a known Alembic/Postgres limitation — `op.drop_table()` has no column-type awareness). A downgrade-then-upgrade cycle failed with `type already exists` until explicit `DROP TYPE` statements were added to the migration by hand.
- Full round-trip confirmed: `alembic upgrade head` → `alembic downgrade base` → `alembic upgrade head`, clean both directions, on both `interviewiq` and `interviewiq_test`.
- `ruff check .` and `black --check .` both pass (generated migration files are excluded from both — see `pyproject.toml`).
- `pytest` passes, hitting a real health check against real Postgres/Redis.
- `docker compose build backend` succeeds; `docker compose up` brings up postgres + redis + backend, and `GET /api/v1/health` returns `{"status": "ok", ...}` over the Docker network.

## Explicitly not in this scaffold

Per the task: no business logic. No feature routers beyond health, no concrete repositories beyond the generic base, no agent implementations, no code execution, no auth endpoints. Every one of those has a stub, a `Protocol`, or an empty package waiting for the module that owns it — see [../docs/Roadmap.md](../docs/Roadmap.md).
