# InterviewIQ AI — Backend

FastAPI backend for InterviewIQ AI. **Module 1** built the architecture, database schema, and infrastructure wiring. **Module 2** (this state of the repo) adds production authentication and user identity: registration, login, JWT access/refresh tokens, RBAC, logout, password reset, and a Google OAuth integration boundary. See [../docs/Roadmap.md](../docs/Roadmap.md) for what comes next, and [../docs/Architecture.md](../docs/Architecture.md) / [../docs/Database.md](../docs/Database.md) / [../docs/API.md](../docs/API.md) for the design this implements.

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
| `user.py` | `users`, `refresh_tokens`, `password_reset_tokens` (added in Module 2 — not in Database.md's original table, see Architecture decisions below) |
| `resume.py` | `resumes`, `resume_skills`, `resume_projects`, `resume_experience`, `resume_gap_analysis` |
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
| `services/auth_service.py` | `AuthService` — the auth use-case layer: register, login, refresh (with rotation), logout, Google login/register, password reset request/confirm. Owns its own transactions (one commit per public method); routers call exactly these methods, never SQLAlchemy or `app.core.security` directly. |
| `services/email.py` | `EmailProvider` protocol + `ConsoleEmailProvider` (the only implementation right now — see "Password reset strategy" below). |
| `services/oauth.py` | `GoogleOAuthProvider` — Authorization Code flow boundary (`build_authorization_url`, `exchange_code`) — see "Google OAuth status" below. |

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
| `deps.py` | Every shared FastAPI dependency: `DbSession`, `RedisClient`, `get_current_user`/`CurrentUser` (decodes a bearer access JWT, loads the `User` row), `require_role(*roles)` (403 role-authorization factory), `get_auth_service`/`get_email_provider`/`get_google_oauth_provider` (config-driven), `get_job_runner`/`get_code_executor`, and `db_healthcheck`/`redis_healthcheck`. |
| `v1/health.py` | `GET /health` — pings Postgres and Redis rather than just returning 200. |
| `v1/auth.py` | Auth router (`/auth/*`) — register, login, refresh, logout, Google OAuth login/callback, password-reset request/confirm. Thin: parses the request, calls one `AuthService` method, shapes the response. |
| `v1/users.py` | `GET /users/me` — returns `UserPublic` for the authenticated user. |
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

### `tests/`

| File | Purpose |
|---|---|
| `conftest.py` | Loads `.env.test` *before* anything imports `app.core.config` (import order matters here — see the `noqa: E402`s), then provides an `httpx.AsyncClient` fixture wired to the app via `ASGITransport` (no real HTTP server needed for tests). Also: an autouse fixture that truncates `users` (cascading to `refresh_tokens`/`password_reset_tokens`) before every test and disposes the process-level DB engine after each test — see the fixture's docstring for why disposal is necessary on top of truncation (pytest-asyncio gives every test its own event loop; pooled asyncpg connections are bound to the loop that opened them). `FakeEmailProvider` — an in-memory `EmailProvider` double used via `app.dependency_overrides` so password-reset tests can read the raw reset token without it ever touching a log. |
| `test_health.py` | Exercises `GET /health` against real Postgres + Redis. |
| `test_auth.py` | Registration, login, JWT (valid/invalid/expired/wrong-type), refresh rotation and reuse-rejection, `require_role`, logout + session revocation, password reset (request/confirm/single-use/token-invalidation-of-sessions), the Google OAuth boundary (503 when unconfigured, unverified-email link refusal), and targeted security assertions (Argon2 hash, hashed-not-raw token storage, redacted validation errors). 33 tests total. |

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

## What was actually verified, not just written

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

## Explicitly not in this milestone

Per the task: no frontend, no Resume Intelligence, no Interview Planner, no LangGraph agents, no interview functionality. Within auth itself: no `POST /auth/verify-email` or `PATCH /users/me` (not in the required endpoint list); no production email provider; Google OAuth needs real credentials to exercise end-to-end; no recruiter/admin endpoints yet (RBAC dependency exists and is tested, nothing depends on it yet — see Features.md, marked "Later"). See [../docs/Roadmap.md](../docs/Roadmap.md) for what comes next.
