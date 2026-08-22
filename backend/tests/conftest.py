"""Loads .env.test before anything imports app.core.config, so the whole
test suite runs against the test database/Redis DB, never dev or prod.
"""

from collections.abc import AsyncGenerator
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env.test", override=True)

import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.api.deps import get_email_provider  # noqa: E402
from app.cache.redis_client import get_redis_pool  # noqa: E402
from app.db.session import get_engine, get_session_factory  # noqa: E402
from app.execution.fake_executor import get_fake_code_executor  # noqa: E402
from app.main import app  # noqa: E402
from app.services.code_evaluation.fake_provider import (  # noqa: E402
    get_fake_code_evaluation_provider,
)
from app.services.coding.catalog_seed import seed_coding_catalog  # noqa: E402
from app.services.email import EmailProvider  # noqa: E402
from app.services.interview_intelligence.fake_provider import (  # noqa: E402
    get_fake_interview_agent_provider,
)
from app.services.planning.catalog_seed import seed_catalog  # noqa: E402
from app.services.resume_intelligence.fake_provider import (  # noqa: E402
    get_fake_resume_intelligence_provider,
)


class FakeEmailProvider(EmailProvider):
    """Captures "sent" emails in memory instead of the console mock, so
    tests can assert on the reset token without ever needing it to appear
    in logs/stdout (see app/services/email.py's ConsoleEmailProvider
    docstring for why the real mock deliberately never exposes it there).
    """

    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    async def send_password_reset_email(self, *, to: str, reset_token: str) -> None:
        self.sent.append((to, reset_token))


@pytest.fixture(autouse=True)
async def _clean_state_between_tests() -> AsyncGenerator[None]:
    """Every test starts with empty auth tables — cascades to
    refresh_tokens/password_reset_tokens via their FK to users.

    Also disposes the (process-level, @lru_cache'd) Postgres engine's and
    Redis pool's connections after each test. pytest-asyncio gives every
    test function its own event loop; both asyncpg connections and
    redis.asyncio connections are bound to the loop that opened them, so a
    pooled connection left open past its test's loop teardown breaks the
    next test that reuses it ("attached to a different loop" / "Event loop
    is closed"). Disposing here runs inside the still-live loop, so each
    pool simply opens fresh connections against the next test's loop on
    demand — this is the pattern SQLAlchemy's own docs recommend for an
    engine reused across multiple event loops, applied to both pools we
    cache at process scope.

    The Redis side of this went undetected until a test started issuing a
    real Redis command (most tests never touch Redis at all, and one
    real command was never followed by another in the same run) — see
    test_auth.py's Google OAuth state tests, which were the first to
    surface it.
    """
    engine = get_engine()
    async with engine.begin() as conn:
        # Cascades to resumes (and every resume_* child table) via their
        # FK to users — Module 3's tables need no separate truncation.
        await conn.execute(text("TRUNCATE TABLE users RESTART IDENTITY CASCADE"))
    # The background resume-processing job builds its ResumeIntelligenceProvider
    # via app/services/resume/factories.py, outside FastAPI's DI — there's no
    # app.dependency_overrides hook for it, so tests instead mutate this
    # module-level fake singleton's fail/timeout/malformed flags directly.
    # Reset here so one test's "simulate a Gemini timeout" can't leak into
    # the next test's upload.
    get_fake_resume_intelligence_provider().reset()
    # Module 5 — same rationale: the graph's nodes call this provider
    # directly (not through app.dependency_overrides), so one test's
    # forced score/failure flags must never leak into the next.
    get_fake_interview_agent_provider().reset()
    # Module 6 — same rationale again: the background execution job builds
    # both of these itself (app/jobs/coding_execution.py), outside FastAPI's
    # DI, so their fail/timeout/forced_* flags are reset here too.
    get_fake_code_executor().reset()
    get_fake_code_evaluation_provider().reset()
    yield
    await engine.dispose()
    await get_redis_pool().disconnect()


@pytest.fixture(autouse=True)
async def _seed_catalog() -> None:
    """Module 4 — companies/roles/interview_templates/template_rounds are
    shared catalog data, not user data, so the truncation fixture above
    never touches them. seed_catalog() is an idempotent upsert (see
    app/services/planning/catalog_seed.py), so reseeding before every test
    is always safe (a cheap no-op after the first run within a test
    session), not just a first-run optimization — this keeps every test
    independent of run order/selection instead of relying on a
    session-scoped fixture interacting with pytest-asyncio's per-test
    event loop (see the truncation fixture's docstring on why that's
    fragile here).
    """
    session_factory = get_session_factory()
    async with session_factory() as session:
        await seed_catalog(session)


@pytest.fixture(autouse=True)
async def _seed_coding_catalog() -> None:
    """Module 6 — coding_problems/coding_problem_test_cases are shared
    catalog data too (same reasoning as _seed_catalog above): not touched
    by the users TRUNCATE, idempotent to reseed before every test.
    """
    session_factory = get_session_factory()
    async with session_factory() as session:
        await seed_coding_catalog(session)


@pytest.fixture
def fake_email_provider() -> FakeEmailProvider:
    return FakeEmailProvider()


@pytest.fixture
async def client(fake_email_provider: FakeEmailProvider) -> AsyncGenerator[AsyncClient]:
    app.dependency_overrides[get_email_provider] = lambda: fake_email_provider
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
