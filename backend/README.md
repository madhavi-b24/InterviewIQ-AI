# InterviewIQ AI — Backend

FastAPI backend for InterviewIQ AI. **Module 1** built the architecture, database schema, and infrastructure wiring. **Module 2** added production authentication and user identity. **Module 3** (this state of the repo) adds Resume Intelligence: authenticated PDF upload, secure validation, deterministic text extraction, section detection, evidence-grounded structured extraction via Gemini, skill normalization, role-readiness analysis, and an explainable interview-difficulty recommendation. See [../docs/Roadmap.md](../docs/Roadmap.md) for what comes next, and [../docs/Architecture.md](../docs/Architecture.md) / [../docs/Database.md](../docs/Database.md) / [../docs/API.md](../docs/API.md) for the design this implements.

## Stack

FastAPI · Python 3.12 · [uv](https://docs.astral.sh/uv/) · PostgreSQL + SQLAlchemy 2.0 (async) · Alembic · Redis · ChromaDB (client) · pypdf · Gemini (`google-genai`) · LangGraph · Ruff + Black · pytest

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

### Auth-relevant environment variables

Every field below lives in `app/core/config.py` and has a safe local default in `.env.example`. **Never commit real secrets** — `.env`/`.env.test` are gitignored.

| Variable | Purpose |
|---|---|
| `JWT_SECRET_KEY` | HMAC signing key for access/refresh JWTs. Must be a long random value in any real environment — the `.env.example` value is a placeholder. |
| `JWT_ALGORITHM` | `HS256` by default. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Access token lifetime (default 15). |
| `REFRESH_TOKEN_EXPIRE_DAYS` | Refresh token lifetime (default 30). |
| `PASSWORD_RESET_TOKEN_EXPIRE_MINUTES` | Password-reset token lifetime (default 30). |
| `EMAIL_PROVIDER` | Only `console` exists right now — logs that a reset email was "sent" without sending real email or ever logging the token. See "Password reset" below. |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` / `GOOGLE_REDIRECT_URI` | Unset by default. `GET /auth/google/login` and `/auth/google/callback` return `503 SERVICE_UNAVAILABLE` until all three are set — see "Google OAuth status" below. |

### Resume Intelligence–relevant environment variables (Module 3)

| Variable | Purpose |
|---|---|
| `GEMINI_API_KEY` | Required for real resume analysis (`RESUME_INTELLIGENCE_PROVIDER=gemini`, the default). Unset by default — see "Gemini configuration" below for what happens without it. |
| `GEMINI_MODEL` | Structured-extraction model, default `gemini-2.5-flash`. |
| `GEMINI_EMBEDDING_MODEL` | Embedding model for `resume_embeddings`, default `text-embedding-004`. |
| `RESUME_STORAGE_BACKEND` | `local` only for now — see "Storage strategy" below. |
| `RESUME_STORAGE_LOCAL_DIR` | Where `LocalResumeStorage` writes files, default `./data/resumes` (gitignored). |
| `RESUME_MAX_UPLOAD_MB` | Upload size cap, default `5`. |
| `RESUME_INTELLIGENCE_PROVIDER` / `RESUME_EMBEDDING_PROVIDER` | `gemini` (default) or `fake`. `fake` exists only for the background job to be driven deterministically in tests (`.env.test`) — `app/services/resume/factories.py` refuses to construct it under `ENVIRONMENT=production`, mirroring `ConsoleEmailProvider`'s guard. |
| `RESUME_INTELLIGENCE_TIMEOUT_SECONDS` | Gemini extraction call timeout, default `45`. |

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
| `security.py` | JWT creation/verification (`create_access_token`, `create_refresh_token`, `decode_token`) and password hashing (`hash_password`/`verify_password`, Argon2id). Also `hash_token`/`generate_opaque_token` for refresh/reset tokens — see "Authentication architecture" below. Pure infrastructure; use-case rules live in `services/auth_service.py`. |
| `exceptions.py` | `AppError` and subclasses (`NotFoundError`, `ConflictError`, `UnauthorizedError`, `ForbiddenError`, `ServiceUnavailableError`) plus the FastAPI exception handlers that turn them into the `{"error": {...}}` envelope defined in API.md §0. The validation-error handler also redacts password/token fields from the echoed `"input"` value — see "Security decisions" below. |

### `app/db/`, `app/cache/`, `app/vectorstore/`, `app/storage/` — datastore/blob connections

| File | Purpose |
|---|---|
| `db/base.py` | `Base` (SQLAlchemy declarative base) and two mixins — `UUIDPrimaryKeyMixin`, `TimestampMixin` — that encode Database.md §0's conventions (UUID PKs, `created_at`/`updated_at`) once instead of repeating them in 29 model classes. |
| `db/session.py` | Async engine + session factory (`get_db_session`), cached per-process. Routes never import the engine directly — always through this, so tests can override the dependency. |
| `cache/redis_client.py` | Async Redis connection pool + `get_redis` dependency. |
| `vectorstore/client.py` | ChromaDB `HttpClient` wrapper — connection only. We depend on the `chromadb-client` package (thin HTTP client) rather than full `chromadb`, since we always talk to the separate ChromaDB container and never embed it in-process; this also sidesteps `chromadb`'s native `hnswlib` dependency, which needs a C++ toolchain to build from source, and it means Chroma has no local embedding function — see `resume_embeddings.py` below. |
| `vectorstore/resume_embeddings.py` | *(Module 3)* `ResumeEmbeddingIndex` — idempotent upsert/delete/query against the `resume_embeddings` collection (Database.md §9), every id/metadata row carrying `user_id` + `resume_id` so cross-user retrieval is structurally impossible through this class. `build_evidence_chunks_from_profile()` assembles chunks from persisted skill/project/experience/certification evidence. |
| `storage/base.py` | *(Module 3)* `ResumeStorage` protocol (`save`/`read`/`delete`) — the seam an object-storage backend (Azure Blob/S3) plugs into later without touching `ResumeService`. |
| `storage/local.py` | *(Module 3)* `LocalResumeStorage` — the MVP backend (`RESUME_STORAGE_BACKEND=local`). Storage keys are always server-generated (`{user_id}/{uuid4().hex}.pdf`), never a client filename; `_resolve()` still defends in depth against path traversal. |

### `app/models/` — SQLAlchemy ORM, one-to-one with Database.md

Every table in Database.md §2–§8 has a corresponding model. Split by domain, matching the doc's section structure:

| File | Tables |
|---|---|
| `enums.py` | Every Postgres ENUM as a Python `StrEnum`, plus `pg_enum()` — a helper that makes SQLAlchemy store each enum's lowercase `.value` (`"local"`, `"google"`) as the DB label. **Without this, SQLAlchemy defaults to storing the Python member's `.name`** (`"LOCAL"`, `"GOOGLE"`) instead, which would silently diverge from what Database.md documents. Caught this during verification, not by inspection — see below. Also `SkillCategory` (Module 3). |
| `user.py` | `users`, `refresh_tokens`, `password_reset_tokens` (added in Module 2 — not in Database.md's original table, see Architecture decisions below) |
| `resume.py` | `resumes`, `resume_skills`, `resume_projects`, `resume_experience`, `resume_gap_analysis`, plus *(Module 3, new tables)* `resume_education`, `resume_certifications`, `resume_achievements`. See Database.md §3 for the full additive column list. |
| `planning.py` | `companies`, `roles`, `interview_templates`, `template_rounds` |
| `interview.py` | `interview_sessions`, `interview_rounds`, `questions`, `question_test_cases`, `answers`, `code_submissions`, `code_submission_test_results` |
| `evaluation.py` | `answer_evaluations`, `coding_evaluations` |
| `report.py` | `interview_reports`, `report_section_scores`, `report_weak_areas`, `report_strong_areas`, `learning_roadmaps`, `roadmap_items` |
| `progress.py` | `skill_progress`, `company_readiness`, `user_progress_snapshots` |
| `__init__.py` | Imports every model module so `Base.metadata` is fully populated and cross-file string relationships (e.g. `relationship("Role")`) resolve. Alembic's `env.py` imports *this* package, not individual model files. |

### `app/repositories/`, `app/services/` — application layers

| File | Purpose |
|---|---|
| `repositories/base.py` | Generic `BaseRepository[ModelT]` (get by id, add, list all) — the one piece of the repository pattern that's truly generic. |
| `repositories/user.py` | `UserRepository` (`get_by_email`, `get_by_google_id`), `RefreshTokenRepository` (`get_by_token_hash`, `revoke`), `PasswordResetTokenRepository` (`get_by_token_hash`, `mark_used`) — the first concrete repositories, added for Module 2's auth queries. |
| `repositories/resume.py` | *(Module 3)* `ResumeRepository` — every lookup takes `user_id` and filters by it in the query itself (`get_owned`, `get_owned_with_children`, `get_active_for_user`, ...), which is what makes ownership enforcement a property of the query, not something a caller could forget. |
| `services/auth_service.py` | `AuthService` — the auth use-case layer: register, login, refresh (with rotation), logout, Google login/register, password reset request/confirm. Owns its own transactions (one commit per public method); routers call exactly these methods, never SQLAlchemy or `app.core.security` directly. |
| `services/email.py` | `EmailProvider` protocol + `ConsoleEmailProvider` (the only implementation right now — see "Password reset strategy" below). |
| `services/oauth.py` | `GoogleOAuthProvider` — Authorization Code flow boundary (`build_authorization_url`, `exchange_code`) — see "Google OAuth status" below. |
| `services/resume/` | *(Module 3)* The deterministic pipeline stages — see "Resume Intelligence (Module 3)" below for the full file-by-file breakdown. |
| `services/resume_intelligence/` | *(Module 3)* The LLM-backed seam: `ResumeIntelligenceProvider`/`EmbeddingProvider` protocols + Gemini/fake implementations. |

### `app/jobs/`, `app/execution/` — the two pluggable-backend seams

Both follow the same shape: a `Protocol` + config-selected implementation, per Architecture.md §6/§8.1.

| File | Purpose |
|---|---|
| `jobs/base.py` | `JobRunner` protocol (`enqueue(job_name, payload) -> job_id`). |
| `jobs/background_tasks_runner.py` | MVP implementation, wrapping FastAPI's `BackgroundTasks`. `JOB_HANDLERS` now has its first real entry — `process_resume` (Module 3, see below). Swapping to Celery later means writing `CeleryRunner` and flipping `JOB_RUNNER_BACKEND`, not touching any caller. |
| `jobs/resume_processing.py` | *(Module 3)* `process_resume_job` — the resume pipeline's background stage. See "Resume Intelligence (Module 3)" below. |
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
| `deps.py` | Every shared FastAPI dependency: `DbSession`, `RedisClient`, `get_current_user`/`CurrentUser` (decodes a bearer access JWT, loads the `User` row), `require_role(*roles)` (403 role-authorization factory), `get_auth_service`/`get_email_provider`/`get_google_oauth_provider` (config-driven), `get_job_runner`/`get_code_executor`, `get_resume_storage`/`get_resume_embedding_index`/`get_resume_service` (Module 3), and `db_healthcheck`/`redis_healthcheck`. |
| `v1/health.py` | `GET /health` — pings Postgres and Redis rather than just returning 200. |
| `v1/auth.py` | Auth router (`/auth/*`) — register, login, refresh, logout, Google OAuth login/callback, password-reset request/confirm. Thin: parses the request, calls one `AuthService` method, shapes the response. |
| `v1/users.py` | `GET /users/me` — returns `UserPublic` for the authenticated user. |
| `v1/resumes.py` | *(Module 3)* Resume Intelligence router (`/resumes/*`) — upload, list, get, analysis, gap-analysis, delete. Thin, same shape as `v1/auth.py`. |
| `v1/router.py` | Aggregates `v1` routers. |

### `app/main.py`

`create_app()`: FastAPI instance, CORS middleware from `settings.CORS_ORIGINS`, exception handlers registered, `v1` router mounted at `/api/v1`. `lifespan()` configures logging on startup and disposes the DB engine on shutdown.

### `alembic/`

| File | Purpose |
|---|---|
| `env.py` | Async-compatible (`asyncio.run(run_migrations_online())`), imports `app.models.Base` for autogenerate, sources the DB URL from `app.core.config` rather than duplicating it in `alembic.ini`. |
| `script.py.mako` | Template for new migration files — stock Alembic template, included explicitly rather than left to `alembic init` defaults. |
| `versions/..._initial_schema.py` | The baseline migration (Module 1), autogenerated from every model in `app/models/` — creates all 29 tables. |
| `versions/..._add_password_reset_tokens.py` | Module 2 migration — adds `password_reset_tokens` only. No enum columns, so none of the initial migration's manual `DROP TYPE` handling applies here. |
| `versions/..._resume_intelligence.py` | Module 3 migration — additive only (Database.md §3's Module-3-tagged columns/tables + the `resume_skills_category_enum` enum + the `uq_resumes_one_active_per_user` partial index). Verified `upgrade → downgrade → upgrade` and `alembic check` (no drift) on both `interviewiq` and `interviewiq_test`. |

### `tests/`

| File | Purpose |
|---|---|
| `conftest.py` | Loads `.env.test` *before* anything imports `app.core.config` (import order matters here — see the `noqa: E402`s), then provides an `httpx.AsyncClient` fixture wired to the app via `ASGITransport` (no real HTTP server needed for tests). Also: an autouse fixture that truncates `users` (cascading to `refresh_tokens`/`password_reset_tokens`/every `resume_*` table) before every test, resets the fake resume-intelligence singleton (Module 3), and disposes the process-level DB engine after each test — see the fixture's docstring for why disposal is necessary on top of truncation (pytest-asyncio gives every test its own event loop; pooled asyncpg connections are bound to the loop that opened them). `FakeEmailProvider` — an in-memory `EmailProvider` double used via `app.dependency_overrides` so password-reset tests can read the raw reset token without it ever touching a log. |
| `test_health.py` | Exercises `GET /health` against real Postgres + Redis. |
| `test_auth.py` | Registration, login, JWT (valid/invalid/expired/wrong-type), refresh rotation and reuse-rejection, `require_role`, logout + session revocation, password reset (request/confirm/single-use/token-invalidation-of-sessions), the Google OAuth boundary (503 when unconfigured, unverified-email link refusal), and targeted security assertions (Argon2 hash, hashed-not-raw token storage, redacted validation errors). 33 tests total. |
| `pdf_fixtures.py` | *(Module 3)* Hand-rolled minimal-PDF byte builder (no reportlab dependency) — a small well-formed synthetic multi-page resume for a clearly fictional candidate ("Alex Rivera"), a blank/no-text PDF, and wrong-signature/truncated/empty byte fixtures for upload-validation tests. |
| `test_resumes.py` | *(Module 3)* 44 tests across upload validation, ownership, extraction, structured analysis (incl. LLM malformed/timeout/failure paths via the fake provider), skill normalization, versioning, role readiness/difficulty, and security (path traversal, cross-user access). See "Resume Intelligence (Module 3)" below for the full breakdown. |

---

## Authentication (Module 2)

### Architecture

```
Router (app/api/v1/auth.py, users.py)
  → AuthService (app/services/auth_service.py) — owns transactions
    → UserRepository / RefreshTokenRepository / PasswordResetTokenRepository
    → app.core.security (JWT, Argon2, token hashing — no business rules)
    → EmailProvider (password reset)   → app/services/email.py
    → GoogleOAuthProvider (Google login) → app/services/oauth.py
```

### Endpoints (API.md §1)

| Method | Path | Auth | Notes |
|---|---|---|---|
| POST | `/api/v1/auth/register` | none | 201, returns `{user, access_token, refresh_token, token_type}` |
| POST | `/api/v1/auth/login` | none | 200, same shape as register |
| POST | `/api/v1/auth/refresh` | refresh token (body) | 200, rotates — returns a new pair, old one revoked |
| POST | `/api/v1/auth/logout` | access token (header) + refresh token (body) | 204, see "Logout semantics" |
| GET | `/api/v1/auth/google/login` | none | 302 redirect to Google, or 503 if unconfigured |
| GET | `/api/v1/auth/google/callback` | none | 200 JSON tokens, or 503/401 |
| POST | `/api/v1/auth/password-reset/request` | none | 202 always, regardless of whether the email exists |
| POST | `/api/v1/auth/password-reset/confirm` | none | 204, or 401 if the token is invalid/expired/used |
| GET | `/api/v1/users/me` | access token | 200, `UserPublic` (no `password_hash`, ever) |

`POST /auth/verify-email` and `PATCH /users/me` are in API.md but **not implemented** in this milestone — they weren't in the required endpoint list and adding them would have been unrequested scope. Tracked as a TODO.

### JWT strategy

- Two token types, both HS256-signed with `JWT_SECRET_KEY`, both carrying `sub` (user id), `type` (`access`/`refresh`), `iat`, `exp`, and a random `jti`.
- Access tokens are short-lived (15 min default) and fully stateless — `get_current_user` verifies signature + expiry + `type == "access"` and loads the user row; no DB lookup of the token itself.
- The `jti` claim exists purely to guarantee uniqueness: `python-jose` truncates `iat`/`exp` to whole-second Unix timestamps, so two tokens minted for the same user within the same second would otherwise be byte-identical and collide on `refresh_tokens.token_hash`'s unique index (a real bug hit and fixed during this milestone's own test run — see `app/core/security.py`).

### Refresh-token strategy

Refresh JWTs are **hybrid**: stateless enough to self-verify (signature/expiry), but every one issued is also persisted as a `refresh_tokens` row keyed by `SHA-256(raw_token)` (never the raw token) with `expires_at`/`revoked_at`. `POST /auth/refresh`:

1. Decodes the JWT (rejects bad signature/expiry/wrong type).
2. Looks up the DB row by hash; rejects if missing, revoked, or expired there too.
3. **Rotates**: revokes that row, mints a brand-new access+refresh pair, persists the new row.

A replayed old refresh token fails at step 2 even though its JWT signature/expiry still check out — the DB row, not the JWT alone, is the source of truth for whether a session is still alive. This is what makes reuse-after-rotation and reuse-after-logout both fail with `401`, tested explicitly in `test_auth.py`.

### Logout semantics

`POST /auth/logout` revokes exactly the refresh **session** named by the `refresh_token` in the request body (only if it belongs to the caller — cross-user revocation attempts are silently ignored, not distinguished by response). It does **not** and cannot invalidate the access token used to authenticate the logout call itself — that token is stateless and remains valid until it naturally expires (at most `ACCESS_TOKEN_EXPIRE_MINUTES`). Clients must discard both tokens locally; the server-side guarantee is only that the refresh session can no longer mint new access tokens. This is a deliberate, documented tradeoff, not an oversight — fully revocable access tokens would require a DB check on every authenticated request, which was ruled out to keep `get_current_user` stateless per Architecture.md.

### Password-reset strategy

- `POST /password-reset/request` always returns `202` with the same body whether or not the email exists — no user-enumeration oracle.
- On a real match, a `secrets.token_urlsafe(32)` opaque token is generated, its SHA-256 hash stored in `password_reset_tokens` (`expires_at` = `PASSWORD_RESET_TOKEN_EXPIRE_MINUTES`, `used_at` nullable), and the raw token is handed to `EmailProvider.send_password_reset_email`.
- `POST /password-reset/confirm` checks the token is unexpired and unused (single-use, enforced by `used_at`), then rehashes the new password and **revokes every existing refresh session for that user** — a password reset is treated as a signal the old password may be compromised.
- `EMAIL_PROVIDER=console` is the only implementation: `ConsoleEmailProvider` logs that a reset email was "sent" (recipient only) and **never logs or prints the raw token** — stdout in a running container is itself a captured log stream, so printing the token there would violate the same "never log reset tokens" rule as structlog would. It also refuses to run under `ENVIRONMENT=production`, failing fast instead of silently discarding every reset email. Tests observe the raw token via a dependency-injected `FakeEmailProvider` test double instead (see `tests/conftest.py`), never via logs.
- No production email provider (SES/SendGrid/Postmark/...) is implemented — out of scope for this milestone; `EmailProvider` is the seam a real one plugs into later.

### Google OAuth status

**Fully implemented as an integration boundary, inert without real credentials.** `GoogleOAuthProvider` (`app/services/oauth.py`) implements the complete Authorization Code flow — building the consent URL, exchanging a code for tokens, fetching userinfo — over `httpx`. The router wires CSRF protection via a short-lived, single-use `state` nonce stored in Redis.

- `GET /auth/google/login` / `/auth/google/callback` return `503 SERVICE_UNAVAILABLE` until `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, and `GOOGLE_REDIRECT_URI` are all set — verified with a live smoke test, no real Google credentials needed for that.
- **What remains**: real Google credentials to exercise the full round trip end-to-end; and the callback currently returns tokens as JSON rather than redirecting to a frontend route, because no frontend exists yet to redirect to — a future frontend module will likely want `{FRONTEND_URL}/oauth/callback#access_token=...`-style redirect instead (tracked as a TODO in `app/api/v1/auth.py`, not invented speculatively here).
- Account linking: a Google sign-in only attaches to an existing local account by email match if Google reports `email_verified: true` for that email; otherwise it's refused with `401` rather than silently linking (an unverified email is not proof of ownership) — see `AuthService.login_or_register_google_user` and its dedicated tests.

### Role-based access control

The platform's standardized internal roles are **`candidate`** (default) / **`recruiter`** / **`admin`** — this is final, matching `users_role_enum` as already migrated in Module 1. `candidate` is the umbrella role for anyone taking interviews, whether a student or an active job seeker; there is no separate "student" role internally. `require_role(*roles)` in `app/api/deps.py` is the reusable authorization dependency: `401` (via `get_current_user`) for missing/invalid tokens, `403` (`ForbiddenError`) for an authenticated user whose role isn't allowed. No recruiter/admin endpoints exist yet (per scope — Features.md marks that "Later"), so `require_role` is exercised directly in tests rather than through a real gated route; the dependency itself is production code, ready for the first admin/recruiter endpoint to depend on it.

---

## Resume Intelligence (Module 3)

### Architecture

```
Router (app/api/v1/resumes.py)
  → ResumeService (app/services/resume/resume_service.py) — upload/list/get/delete/gap-analysis, owns transactions
    → ResumeRepository (app/repositories/resume.py) — every query scoped by user_id
    → ResumeStorage (app/storage/) — save/read/delete PDF bytes
    → app/services/resume/pdf.py — magic-byte/trailer/structure validation (upload-time, synchronous)

JobRunner.enqueue("process_resume", ...) → app/jobs/resume_processing.py (background)
  → ResumeStorage.read()
  → app/services/resume/pdf.py — extract_pdf_text() (deterministic, pypdf)
  → app/services/resume/section_detection.py — detect_sections()
  → ResumeIntelligenceProvider (app/services/resume_intelligence/) — Gemini structured extraction
  → app/services/resume/skill_normalization.py — normalize_skill()
  → persists resume_education/skills/projects/experience/certifications/achievements
  → ResumeEmbeddingIndex (app/vectorstore/resume_embeddings.py) — best-effort ChromaDB indexing

ResumeService.generate_role_readiness()
  → app/services/resume/role_profiles.py — internal competency profiles
  → app/services/resume/readiness.py — compute_role_readiness() + compute_interview_level() (pure, no LLM call)
  → persists resume_gap_analysis (replaces the single row — see Database.md §3)

app/services/resume/interview_context.py — read-only integration boundary for the future
Interview Engine (module §13); not wired to any endpoint yet.
```

### Processing pipeline and states

```
uploaded (parsed_status=pending)
  -> processing (extracting text)
       -> [scanned/no text] -> failed, processing_error explains OCR would be required, STOP
       -> raw_text + detected_sections persisted
  -> processing (AI analysis)
       -> [Gemini timeout/failure/malformed] -> failed, processing_error set;
          raw_text/detected_sections from the step above are NOT rolled back
       -> [success] -> structured rows persisted -> done
  -> (best-effort, never changes the above) ChromaDB indexing
```

Database.md's `parsed_status` enum (`pending`/`processing`/`done`/`failed`, from Module 1) is reused as-is — `processing` covers both the extraction and AI-analysis sub-stages; which sub-stage failed is communicated through `processing_error`'s text, not a fifth enum value, so no schema change was needed for the state model itself. `GET /resumes/{id}` is the poll target, matching API.md.

**Transaction boundaries** (`app/jobs/resume_processing.py`): one commit after `status -> processing`, one after raw text/sections are persisted (this is the commit that survives an AI failure), one after either AI success (structured rows + `status -> done`) or AI failure (`status -> failed`), and a final best-effort commit for `embeddings_indexed_at` that never affects `parsed_status` either way.

### Storage strategy

`ResumeStorage` (`app/storage/base.py`) is a `Protocol` — `save`/`read`/`delete` — with `LocalResumeStorage` (`app/storage/local.py`) as the only implementation right now, selected via `RESUME_STORAGE_BACKEND=local`. Storage keys are always server-generated (`{user_id}/{uuid4().hex}.pdf`) in `ResumeService.upload`, never derived from the client's filename, and `LocalResumeStorage._resolve()` additionally rejects any key that would resolve outside its configured root — defense in depth even though the key is never client-controlled. `resumes.file_url` stores this logical key, not an absolute filesystem path, and no API response ever includes it. An object-storage backend (Azure Blob/S3) is a second class against the same Protocol plus a config flip — no change to `ResumeService`, the background job, or any router.

### Gemini configuration

`ResumeIntelligenceProvider` (`app/services/resume_intelligence/provider.py`) is a `Protocol`; `GeminiResumeIntelligenceProvider` (`gemini_provider.py`) is the real implementation, using the `google-genai` SDK's structured-output mode (`response_schema=ExtractedProfile`, `response_mime_type="application/json"`), `temperature=0.1`, an `asyncio.wait_for` timeout (`RESUME_INTELLIGENCE_TIMEOUT_SECONDS`, default 45s), and exactly one retry — only for `ServerError` (5xx/transient); a `ClientError` (bad key, bad request) or a schema-validation failure is never retried, since retrying identically wouldn't help. The system prompt explicitly requires every extracted item to carry `evidence` and forbids inventing anything not in the resume text. Never logs the API key or resume text — only its length (`resume_chars=len(...)`).

A second provider, `EmbeddingProvider` (`embedding_provider.py`), computes precomputed vectors for ChromaDB (see "ChromaDB usage" below) via `GEMINI_EMBEDDING_MODEL` (default `text-embedding-004`).

**Without `GEMINI_API_KEY` configured:** `GeminiResumeIntelligenceProvider.__init__` raises immediately (caught by the job, which marks the resume `failed` with a clear message) rather than silently returning empty/fabricated data — the endpoint stays usable (upload/list/get/delete all still work), only AI analysis is unavailable.

### Fake providers (tests only)

`RESUME_INTELLIGENCE_PROVIDER` / `RESUME_EMBEDDING_PROVIDER` accept `fake` in addition to `gemini`. `app/services/resume/factories.py` — the single place both `app/api/deps.py` (request handlers) and the background job build these objects — refuses to construct the fake in `ENVIRONMENT=production`, exactly mirroring `ConsoleEmailProvider`'s guard (see Module 2 above). `.env.test` sets both to `fake`. Because the background job builds its own provider instance outside FastAPI's dependency-injection graph (there is no request context by the time it runs), there's no `app.dependency_overrides` hook for it — instead, `FakeResumeIntelligenceProvider` is a module-level singleton (`get_fake_resume_intelligence_provider()`) whose `.fail`/`.timeout`/`.malformed` flags tests set directly before an upload, and an autouse `conftest.py` fixture resets between tests.

### Evidence-grounding strategy

Every fact-bearing row — `resume_skills`, `resume_projects`, `resume_experience`, `resume_education`, `resume_certifications`, `resume_achievements` — has an `evidence_text` column: the resume fragment it was extracted from. The Gemini system prompt requires this for every item and instructs the model to omit an item entirely rather than include it without supporting text. `GET /resumes/{id}/analysis` returns `evidence` on every item. This is what lets a future interview question be grounded in what the candidate actually claimed (module §6, §13), and it's enforced structurally (a schema field every extraction path must populate), not just a prompting convention — `test_no_hallucinated_skills` in `test_resumes.py` asserts every persisted skill's raw text actually appears in the resume's own Skills section.

### Skill-normalization strategy

`app/services/resume/skill_normalization.py`'s `normalize_skill()` looks up a lowercased, period-stripped, whitespace-collapsed form of the raw skill text against a curated alias table in `app/services/resume/data/skill_aliases.json` (~90 entries across languages/frameworks/databases/cloud/AI-ML/dev-tools) — e.g. `"JS"` / `"js"` → `{"canonical": "JavaScript", "category": "programming_language"}`. A skill with no curated alias is **kept as-is** (cosmetic whitespace cleanup only), tagged `category=other`, `matched=False` — never dropped, never force-merged into an unrelated canonical name, and never fuzzy-matched (only exact curated aliases). The alias table is a maintainable data file specifically so the normalization logic in code never grows a per-technology `if` chain.

### Role-readiness algorithm

`app/services/resume/role_profiles.py` loads `data/role_profiles.json` — five internal InterviewIQ competency profiles (`software_engineer`, `backend_engineer`, `ai_engineer`, `ml_engineer`, `data_engineer`), each a `required_skills`/`nice_to_have_skills` list of canonical skill names. **These are InterviewIQ's own baseline, explicitly not a claim about any employer's actual hiring bar.** `compute_role_readiness()` (`readiness.py`) does case-insensitive set comparison against the candidate's normalized skills: `matching_skills` = required ∩ owned, `missing_skills` = required − owned, `strengths` = nice-to-have ∩ owned, `focus_areas` = missing required (or, if none missing, the next tier of nice-to-haves not yet owned).

### Difficulty-recommendation algorithm

`compute_interview_level()` (`readiness.py`) is a deterministic weighted score, not an LLM guess:

```
breadth_ratio     = (# required skills matched) / (# required skills)
depth_ratio       = min(1.0, project_count * 0.25 + experience_count * 0.35)
complexity_ratio  = min(1.0, keyword_hits / 3)   # "distributed", "scaled", "production", "optimized", ...

score = 0.45 * breadth_ratio + 0.30 * depth_ratio + 0.25 * complexity_ratio
level = easy if score < 0.35 else medium if score < 0.70 else hard   # Beginner / Intermediate / Advanced
```

`confidence` is computed separately from `level` — it reflects how much resume material there was to reason over (skills + 2×projects + 2×experience entries), capped low for a sparse resume even if its score happens to land in a higher band, so a thin resume never gets reported as confidently "Advanced." Every response includes `reasons`: the concrete signals behind the number (e.g. `"Matches 4/7 core skills for Backend Engineer"`, `"Found 3 indicator(s) of production/scale complexity"`) — an explanation, not a bare score, matching Vision.md's product principle.

### Gemini integration status

**Fully implemented, verified with mocked/fake providers only — not exercised against a live Gemini API in this environment** (no `GEMINI_API_KEY` available here). What *was* verified live: `GeminiResumeIntelligenceProvider(settings)` and `GeminiEmbeddingProvider(settings)` construct correctly and raise `ResumeIntelligenceProviderError`/`EmbeddingProviderError` immediately when `GEMINI_API_KEY` is unset (see "What was actually verified" below) — this is the fail-fast path a misconfigured deployment hits. The full extraction/embedding pipeline was verified end-to-end against `FakeResumeIntelligenceProvider`/`FakeEmbeddingProvider` (44 tests in `test_resumes.py`).

### ChromaDB usage/status

**Genuinely used, not indexed "because a vector database exists."** `resume_embeddings` (Database.md §9) stores one vector per skill/project/experience/certification evidence chunk, embedded via `EmbeddingProvider` (precomputed — `chromadb-client`'s thin HTTP client has no local embedding function, see `vectorstore/client.py`). Indexing is idempotent (`reindex_resume` deletes-then-upserts by `resume_id`) and every id/metadata row carries `user_id` — this was verified **live against the running ChromaDB container** (not just unit-tested): index → query (finds the indexed chunks) → query as a different `user_id` (returns nothing) → reindex with fewer chunks (stale ones gone) → delete (nothing left). Nothing reads from this collection yet — indexing is best-effort (wrapped in its own try/except, never affects `parsed_status`) and prepared purely as the boundary the future Interview Engine's Knowledge Agent will read from, per module §14's explicit instruction not to over-build this ahead of a real consumer.

### Security protections

- **File upload**: magic-byte (`%PDF-`) + trailer (`%%EOF`) + a real (if shallow) `pypdf` structural parse, all before anything is persisted; size cap (`RESUME_MAX_UPLOAD_MB`, default 5MB) enforced via a bounded `file.read(max_bytes + 1)` so an oversized upload is never fully buffered; extension + declared-MIME-type checks; encrypted/password-protected PDFs rejected.
- **Path traversal**: the client's filename is sanitized for *display only* (`_sanitize_filename` strips any `/`/`\` path components and control characters) and never used to construct a storage path — the storage key is always server-generated. `LocalResumeStorage._resolve()` independently rejects any key resolving outside its root as defense in depth.
- **Ownership / IDOR**: every `ResumeRepository` read/write method takes `user_id` and filters by it in the SQL itself. Every resume endpoint returns `404 RESOURCE_NOT_FOUND` — never `403` — for a resume that exists but isn't the caller's, so a client can't distinguish "not yours" from "doesn't exist."
- **PII / logging**: no endpoint or log line ever includes the full extracted resume text; the Gemini provider logs only character counts. `file_url` (the storage key) is never included in any API response.
- **Deletion**: `DELETE /resumes/{id}` removes the Postgres row (cascading to every child table) inside one transaction, then best-effort-deletes the stored file and ChromaDB vectors *after* that transaction commits — a storage/Chroma hiccup can never leave a resurrected-looking Postgres row.

### Known limitations

- Gemini extraction/embeddings were verified against fake providers only in this environment (no live API key) — see "Gemini integration status" above.
- OCR for scanned/image-only PDFs is explicitly out of scope for this milestone (module §3) — such resumes are marked `failed` with a clear message, not silently mis-processed.
- `pypdf`'s parsing (upload-time validation, background extraction) runs on a thread via `asyncio.to_thread` rather than natively async — appropriate for resume-sized PDFs, but real backpressure under heavy concurrent load would need a bounded thread pool / worker-based execution (same class of concern Module 6 already flags for the code-execution sandbox).
- `resumes.raw_text` (the full extracted text) is intentionally never returned by any API response — only structured, evidence-tagged data is. If a future need arises to show raw text in a UI, that's a new schema field on `ResumeAnalysisResponse`, not a design gap.
- The `resume_embeddings` collection is indexed but not yet queried by anything — by design, per module §14 ("don't index ahead of a real consumer"); the boundary (`ResumeEmbeddingIndex.query`) is ready for the future Knowledge Agent.
- Role competency profiles (`data/role_profiles.json`) are a fixed set of five roles; adding a sixth is a data change, not a code change, but there's no admin UI for it yet (consistent with Features.md marking that "Later").

---

## Manually verifying authentication with Swagger

1. `docker compose up -d` from the repo root (or `uv run uvicorn app.main:app --reload` from `backend/`).
2. Open `http://localhost:8000/docs`.
3. **Register**: `POST /api/v1/auth/register` → Try it out → body `{"email": "you@example.com", "password": "correct-horse-42", "first_name": "Ada", "last_name": "Lovelace"}` → Execute. Expect `201` with `access_token`/`refresh_token`/`user`. Copy `access_token`.
4. Click **Authorize** (top right) → paste the access token (no `Bearer ` prefix needed, Swagger adds it) → Authorize.
5. **Current user**: `GET /api/v1/users/me` → Execute. Expect `200` with your user, no `password_hash` field.
6. **Login**: `POST /api/v1/auth/login` with the same credentials → Execute. Expect a fresh token pair. Copy the new `refresh_token`.
7. **Refresh**: `POST /api/v1/auth/refresh` → body `{"refresh_token": "<paste>"}` → Execute. Expect `200` with a *different* access/refresh pair. Re-running this exact call a second time with the same (now-rotated-away) token should return `401`.
8. **Logout**: `POST /api/v1/auth/logout` → body `{"refresh_token": "<the refresh token from step 7's response>"}` (must still be Authorized from step 4, or re-authorize with the newest access token) → Execute. Expect `204`. Repeating step 7 with that same refresh token now also returns `401`.

Password reset and Google OAuth aren't in the required walkthrough above, but can be sanity-checked too: `POST /auth/password-reset/request` always returns `202`; since `EMAIL_PROVIDER=console` never logs the token (by design — see "Password reset strategy"), retrieving it requires either `tests/test_auth.py`'s `FakeEmailProvider` or a real provider, not Swagger. `GET /auth/google/login` returns `503` until Google credentials are configured.

## Manually verifying Resume Intelligence with Swagger

1. Register/log in per steps 1–4 above and **Authorize** with an access token.
2. **Upload**: `POST /api/v1/resumes` → Try it out → choose a real PDF file for the `file` field → Execute. Expect `201` with `parsed_status: "pending"`. Copy the returned `id`.
3. **Check processing**: `GET /api/v1/resumes/{resume_id}` → Execute, repeat until `parsed_status` is `"done"` (or `"failed"`, with `processing_error` explaining why — e.g. no `GEMINI_API_KEY` configured, or a scanned/image-only PDF).
4. **View analysis**: `GET /api/v1/resumes/{resume_id}/analysis` → Execute. Expect skills/projects/experience/education/certifications/achievements, each with an `evidence` field.
5. **Role readiness**: `POST /api/v1/resumes/{resume_id}/gap-analysis` → body `{"role_key": "backend_engineer"}` (other valid keys: `software_engineer`, `ai_engineer`, `ml_engineer`, `data_engineer`) → Execute. Expect `matching_skills`/`missing_skills`/`strengths`/`focus_areas`, `recommended_difficulty` + `recommended_level_label`, `confidence`, and `reasons`.
6. **Upload a newer version**: repeat step 2 with a different (or the same) PDF. `GET /api/v1/resumes` now lists both — the newer one `is_active: true`, the first `is_active: false`.
7. **Verify history preserved**: `GET /api/v1/resumes/{first_resume_id}/analysis` still returns the first upload's full structured analysis — nothing was destroyed by the second upload.
8. **Ownership check**: register a second account, Authorize with *its* token, then `GET /api/v1/resumes/{resume_id}` using the first account's resume ID → expect `404`, not the first account's data.

Without `GEMINI_API_KEY` configured, step 3 settles on `parsed_status: "failed"` with `processing_error` explaining AI analysis is unavailable — upload/list/get/delete still work end to end; only steps 4–5 have nothing to show.

## What was actually verified, not just written (Module 2)

Every piece of this milestone was run, not just authored:

- `uv sync` installs cleanly (new deps: `argon2-cffi`, `httpx` promoted to a main dependency).
- New migration (`add password reset tokens`) generated with `alembic revision --autogenerate`, then round-tripped on `interviewiq_test`: `upgrade head` → `downgrade -1` → `upgrade head` → `downgrade base` (full stack, including the original migration's enum-drop path) → `upgrade head`. Also applied cleanly to the dev `interviewiq` database.
- `ruff check .` and `black --check .` both pass.
- `pytest` — **33 passed**, 0 failed, covering registration, login, JWT validity/expiry/type-confusion, refresh rotation/reuse-rejection, logout+session revocation, RBAC, password reset (including single-use and session-invalidation-on-reset), the Google OAuth boundary, and targeted security assertions.
- **Found and fixed during this milestone's own verification, not by inspection — four real bugs:**
  1. Refresh-JWT collisions: `python-jose` truncates `iat`/`exp` to whole-second Unix timestamps, so two tokens for the same user minted within the same second were byte-identical, violating `refresh_tokens.token_hash`'s unique index (surfaced by `test_login_success`, which registers then logs in — two token pairs in well under a second). Fixed by adding a random `jti` claim to every token.
  2. `RequestValidationError`'s exception handler crashed with `TypeError: Object of type ValueError is not JSON serializable` — pydantic v2 puts the original exception object under `ctx["error"]` for validators that raise `ValueError` (our password-strength check was the first validator in the codebase to do this). Fixed with `fastapi.encoders.jsonable_encoder`.
  3. Validation errors on `password`/`token` fields echoed the rejected raw value back in the response body's `"input"` key — not the DB, not a log line, but still an unwanted round-trip of a submitted password into an HTTP response. Fixed by redacting `"input"` for a fixed set of sensitive field names in the same handler.
  4. Cross-event-loop asyncpg connection reuse: `app.db.session.get_engine()` is `@lru_cache`d (one pool per process, correct for the real server), but pytest-asyncio gives every test function its own event loop by default — a pooled connection opened under test N's loop broke when reused under test N+1's loop (`RuntimeError: ... attached to a different loop`). Fixed by disposing the engine's pool at the end of every test, while its loop is still alive, so the pool simply reconnects fresh next time (the pattern SQLAlchemy's own docs recommend for reusing an engine across event loops) — see `tests/conftest.py`.
- `docker compose build backend` succeeds (picks up `argon2-cffi`/`httpx`); `docker compose up -d backend` restarts cleanly; `GET /api/v1/health` returns `{"status": "ok", ...}` over the Docker network.
- Full auth flow smoke-tested with real `curl` against the running Docker container (not just pytest): register → duplicate-register (409) → login → `/users/me` with and without a token (200/401) → refresh → replay old refresh token (401) → logout → refresh with the logged-out token (401) → password-reset request for a known and unknown email (both 202) → weak-password register (422, with password redacted from the response) → `/auth/google/login` unconfigured (503).
- Grepped `docker compose logs backend` for `password|token|bearer` after the full smoke run above — the only match is the `to=<email>` line from `ConsoleEmailProvider`; no password, hash, JWT, refresh token, or reset token appears anywhere in the logs.

## What was actually verified, not just written (Module 3)

- `uv sync` installs cleanly (new deps: `pypdf`, `google-genai` + its transitive `google-auth`).
- Migration (`resume intelligence`) autogenerated, hand-adjusted (server defaults, named unique constraint, explicit enum `CREATE`/`DROP TYPE`, partial unique index), then round-tripped on **both** `interviewiq` and `interviewiq_test`: `upgrade head` → `downgrade -1` → `upgrade head` → `downgrade base` → `upgrade head`; `alembic check` reports no drift on either database.
- `ruff check .` and `black --check .` both pass.
- `pytest` — **84 passed** (40 pre-existing Module 1/2 tests + 44 new Module 3 tests), 0 failed — confirms no regression to registration/login/refresh/logout/password-reset/Google-OAuth/`/users/me`/`/health` alongside the new coverage (upload validation, ownership, extraction, structured analysis incl. LLM malformed/timeout/failure, skill normalization, versioning, role readiness/difficulty, security).
- ChromaDB integration verified **live against the running container** (not mocked): indexed real evidence chunks with `FakeEmbeddingProvider`, queried them back, queried as a different `user_id` (empty result — cross-user isolation confirmed), reindexed with fewer chunks (stale ones gone — idempotency confirmed), deleted (nothing left).
- `GeminiResumeIntelligenceProvider`/`GeminiEmbeddingProvider` verified to construct correctly and fail fast (`ResumeIntelligenceProviderError`/`EmbeddingProviderError`, not a crash) when `GEMINI_API_KEY` is unset — **not exercised against the live Gemini API** in this environment (no key available). Full extraction/embedding pipeline behavior verified against the deterministic fake providers instead (44 tests).
- `docker compose build backend` succeeds; `docker compose up -d` (full stack) starts cleanly; `GET /api/v1/health` returns `{"status": "ok", ...}` over the Docker network.
- **Found and fixed during live Docker verification, not caught by `pytest` (which uses fake providers) — two real bugs:**
  1. **Storage permission failure**: `LocalResumeStorage.__init__` calls `mkdir(parents=True, exist_ok=True)` on `RESUME_STORAGE_LOCAL_DIR` (default `/app/data/resumes` inside the container) — but the Dockerfile's `WORKDIR /app` creates `/app` as root, and only the explicitly-copied subdirectories (`.venv`, `app`, `alembic`) are `chown`ed to the non-root `appuser`. Every upload 500'd with `PermissionError: [Errno 13] Permission denied: '/app/data'`. Fixed by pre-creating `/app/data/resumes` with correct ownership in the Dockerfile, and added a named `resume_data` volume in `docker-compose.yml` (matching `postgres_data`/`chroma_data`) so uploaded resumes persist across container recreation.
  2. **Entire resumes API broken without `GEMINI_API_KEY`**: `get_resume_service` (`app/api/deps.py`) originally took a resolved `ResumeEmbeddingIndexDep` as a direct FastAPI dependency parameter — but FastAPI resolves every `Depends()` in a route's tree *before* the endpoint body runs, so constructing `GeminiEmbeddingProvider` (which raises immediately if `GEMINI_API_KEY` is unset) happened on **every** resume request, including upload/list/get, none of which touch embeddings at all. This directly violated module §9 ("the entire endpoint must not become useless if Gemini is temporarily unavailable") — every `POST /resumes` 500'd. Fixed by passing `ResumeService` a lazy `embedding_index_factory` callable instead of a resolved instance; it's now only invoked inside `delete_resume`'s already-best-effort cleanup, where construction failure is just one more thing that path logs and swallows. Verified via `curl` against the running container without a Gemini key: upload → `201 pending` → poll → `failed` with `processing_error: "AI analysis failed: GEMINI_API_KEY is not configured"` (not a 500) → list/get/delete all still work.
- Also caught (by code inspection during self-review, applied before live testing): `_open_reader`'s exception handling caught `pypdf.errors.PdfReadError` but missed `ParseError`/`DependencyError`, which are direct `PyPdfError` subclasses, not `PdfReadError` ones — a malformed PDF tripping one of those would have 500'd instead of returning a clean `422 MALFORMED_PDF`. Broadened to catch `PyPdfError` (the common base). Also offloaded `pypdf`'s CPU-bound parsing (`validate_pdf_upload`, `extract_pdf_text`) onto `asyncio.to_thread` so it never blocks the event loop other requests share.
- Full resume flow smoke-tested with real `curl` against the running Docker container (not just pytest, and without a Gemini key configured — the harder path): register (user A + user B) → upload as A (`201 pending`) → poll (`failed`, clear `processing_error`, not a 500) → list as A → B `GET`s A's resume (`404`) → B `DELETE`s A's resume (`404`) → A still has it (`200`) → unauthenticated upload/list (`401`/`401`) → A deletes own resume (`204`) → A `GET`s the deleted resume (`404`).
- Confirmed the uploaded file was actually written under the container's `resume_data` volume with correct `appuser` ownership (`docker compose exec backend ls /app/data/resumes/`), and that `DELETE` actually removed it from disk.
- Grepped `docker compose logs backend` for `password|bearer` plus the fixture candidate's name/resume-fixture content after the full smoke run above — no match; no resume text, password, or bearer token appears anywhere in the logs.

## Explicitly not in this milestone

**Module 2 (Authentication):** no `POST /auth/verify-email` or `PATCH /users/me` (not in the required endpoint list); no production email provider; Google OAuth needs real credentials to exercise end-to-end; no recruiter/admin endpoints yet (RBAC dependency exists and is tested, nothing depends on it yet — see Features.md, marked "Later").

**Module 3 (Resume Intelligence):** no frontend, no Interview Planner, no LangGraph agents, no interview functionality — per the task, this module stops at the clean integration boundary (`app/services/resume/interview_context.py`) a future Interview Engine will call. No OCR for scanned PDFs (module §3, explicitly deferred). No live Gemini verification in this environment (no API key available — see "Gemini integration status" above). `resume_embeddings` is indexed but not queried by anything yet (module §14). See [../docs/Roadmap.md](../docs/Roadmap.md) for what comes next.
