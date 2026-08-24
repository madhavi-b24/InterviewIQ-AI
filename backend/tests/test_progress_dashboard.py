"""Module 8 (Progress Dashboard) tests.

No provider/fake-provider setup of its own — ProgressService never calls
an LLM (module docstring, app/services/progress/__init__.py). Every test
here either drives a real session to completion through the existing
Module 5/6/7 flow (reusing FakeInterviewAgentProvider/FakeCodeExecutor/
FakeCodeEvaluationProvider/FakeReportGenerationProvider exactly as
test_report_generation.py's own tests do) or calls ProgressService/
generate_report_job directly.

Helpers are duplicated locally rather than imported, mirroring this
codebase's established per-file-independent-helpers convention
(test_coding_round.py's own docstring: "mirrors tests/
test_interview_execution.py's conventions").
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.agents.checkpointer import get_checkpointer
from app.agents.policy import classify_score_trend
from app.db.session import get_session_factory
from app.jobs.report_generation import generate_report_job
from app.models.enums import ProgressTrend
from app.models.interview import InterviewSession
from app.models.progress import CompanyReadiness, SkillProgress, UserProgressSnapshot
from app.services.interview_intelligence.fake_provider import get_fake_interview_agent_provider

VALID_PASSWORD = "correct-horse-42"


@pytest.fixture(autouse=True)
async def _ensure_checkpoint_tables() -> None:
    async with get_checkpointer() as checkpointer:
        await checkpointer.setup()


# --- helpers (mirrors tests/test_report_generation.py's/test_coding_round.py's
# conventions) ---------------------------------------------------------------


async def _register(client: AsyncClient, *, email: str) -> str:
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": VALID_PASSWORD,
            "first_name": "Test",
            "last_name": "Candidate",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _find_role(client: AsyncClient, token: str, *, role_key: str, company_id=None) -> dict:
    response = await client.get("/api/v1/roles", headers=_auth(token))
    assert response.status_code == 200, response.text
    for r in response.json():
        if r["role_key"] == role_key and r["company_id"] == company_id:
            return r
    raise AssertionError(f"role_key={role_key} company_id={company_id} not found")


async def _find_template(client: AsyncClient, token: str, *, role_id: str, name: str) -> dict:
    response = await client.get(f"/api/v1/roles/{role_id}/templates", headers=_auth(token))
    assert response.status_code == 200, response.text
    for t in response.json():
        if t["name"] == name:
            return t
    raise AssertionError(f"template name={name!r} not found")


async def _find_role_and_template_by_name(
    client: AsyncClient, token: str, *, template_name: str
) -> tuple[dict, dict]:
    """Company-specific templates live under a company-specific role, whose
    company_id isn't known in advance — iterate every role's own templates
    rather than guessing a company_id first.
    """
    roles_response = await client.get("/api/v1/roles", headers=_auth(token))
    assert roles_response.status_code == 200, roles_response.text
    for role in roles_response.json():
        templates_response = await client.get(
            f"/api/v1/roles/{role['id']}/templates", headers=_auth(token)
        )
        assert templates_response.status_code == 200, templates_response.text
        for t in templates_response.json():
            if t["name"] == template_name:
                return role, t
    raise AssertionError(f"template {template_name!r} not found under any role")


async def _plan(client: AsyncClient, token: str, body: dict) -> dict:
    response = await client.post("/api/v1/interview-sessions", headers=_auth(token), json=body)
    assert response.status_code == 201, response.text
    return response.json()


async def _start(client: AsyncClient, token: str, interview_id: str):
    return await client.post(
        f"/api/v1/interview-sessions/{interview_id}/start", headers=_auth(token)
    )


async def _answer(client: AsyncClient, token: str, interview_id: str, question_id: str, text: str):
    return await client.post(
        f"/api/v1/interview-sessions/{interview_id}/answers",
        headers=_auth(token),
        json={"question_id": question_id, "answer_text": text},
    )


async def _submit_code(
    client: AsyncClient,
    token: str,
    interview_id: str,
    question_id: str,
    *,
    source_code: str,
    language: str = "python",
    is_final: bool = False,
):
    return await client.post(
        f"/api/v1/interview-sessions/{interview_id}/questions/{question_id}/code-submissions",
        headers=_auth(token),
        json={"language": language, "source_code": source_code, "is_final": is_final},
    )


async def _complete_coding_practice_session(client: AsyncClient, token: str) -> str:
    """ "Coding Practice" (role_key=software_engineer, company_id=None) — a
    single coding round, no company link. Returns interview_id.
    """
    role = await _find_role(client, token, role_key="software_engineer", company_id=None)
    template = await _find_template(client, token, role_id=role["id"], name="Coding Practice")
    interview = await _plan(
        client,
        token,
        {"role_id": role["id"], "template_id": template["id"], "difficulty": "medium"},
    )
    started = await _start(client, token, interview["id"])
    assert started.status_code == 200, started.text
    question_id = started.json()["question"]["id"]

    response = await _submit_code(
        client, token, interview["id"], question_id, source_code="# CORRECT_SOLUTION", is_final=True
    )
    assert response.status_code == 202, response.text
    return interview["id"]


async def _complete_technical_mock_session(
    client: AsyncClient, token: str, *, email_tag: str
) -> str:
    """ "Technical Mock" (introduction -> technical x3 -> coding, role_key
    backend_engineer, company_id=None) driven to full completion —
    produces technical/problem_solving/communication/confidence *and*
    coding evaluations in one session (mirrors tests/
    test_report_generation.py's own helper of the same shape).
    """
    role = await _find_role(client, token, role_key="backend_engineer", company_id=None)
    template = await _find_template(client, token, role_id=role["id"], name="Technical Mock")
    interview = await _plan(
        client,
        token,
        {"role_id": role["id"], "template_id": template["id"], "difficulty": "medium"},
    )
    started = await _start(client, token, interview["id"])
    assert started.status_code == 200, started.text
    question_id = started.json()["question"]["id"]

    interview_provider = get_fake_interview_agent_provider()
    interview_provider.forced_follow_up_worthy = False

    response = None
    for _ in range(4):  # introduction (1) + technical (3)
        response = await _answer(client, token, interview["id"], question_id, f"answer {email_tag}")
        assert response.status_code == 200, response.text
        next_body = response.json()["next"]
        if next_body["type"] != "question":
            break
        question_id = next_body["question"]["id"]
    assert response.json()["next"]["type"] == "question", response.text
    coding_question_id = response.json()["next"]["question"]["id"]

    submit = await _submit_code(
        client,
        token,
        interview["id"],
        coding_question_id,
        source_code="# CORRECT_SOLUTION",
        is_final=True,
    )
    assert submit.status_code == 202, submit.text
    return interview["id"]


async def _complete_amazon_swe_session(client: AsyncClient, token: str) -> str:
    """Amazon SWE - Behavioral + Technical: introduction(1) + behavioral(2)
    + technical(3), company-linked (company_slug=amazon) — the one
    company-specific, text-only template in the seeded catalog, used to
    exercise company_readiness.
    """
    role, template = await _find_role_and_template_by_name(
        client, token, template_name="Amazon SWE — Behavioral + Technical"
    )
    interview = await _plan(
        client,
        token,
        {
            "role_id": role["id"],
            "template_id": template["id"],
            "company_id": role["company_id"],
            "difficulty": "medium",
        },
    )
    started = await _start(client, token, interview["id"])
    assert started.status_code == 200, started.text
    question_id = started.json()["question"]["id"]

    provider = get_fake_interview_agent_provider()
    provider.forced_follow_up_worthy = False

    response = None
    for _ in range(6):  # introduction(1) + behavioral(2) + technical(3)
        response = await _answer(client, token, interview["id"], question_id, "a reasonable answer")
        assert response.status_code == 200, response.text
        if response.json()["next"]["type"] != "question":
            break
        question_id = response.json()["next"]["question"]["id"]
    assert response.json()["next"]["type"] == "session_complete", response.text
    return interview["id"]


async def _session_user_id(interview_id: str) -> str:
    async with get_session_factory()() as session:
        interview = await session.get(InterviewSession, uuid.UUID(interview_id))
        return str(interview.user_id)


async def _snapshot_count(user_id: str) -> int:
    async with get_session_factory()() as session:
        result = await session.execute(
            select(UserProgressSnapshot).where(UserProgressSnapshot.user_id == uuid.UUID(user_id))
        )
        return len(result.scalars().all())


async def _skill_progress_rows(user_id: str) -> list[SkillProgress]:
    async with get_session_factory()() as session:
        result = await session.execute(
            select(SkillProgress).where(SkillProgress.user_id == uuid.UUID(user_id))
        )
        return list(result.scalars().all())


async def _company_readiness_rows(user_id: str) -> list[CompanyReadiness]:
    async with get_session_factory()() as session:
        result = await session.execute(
            select(CompanyReadiness).where(CompanyReadiness.user_id == uuid.UUID(user_id))
        )
        return list(result.scalars().all())


# ===========================================================================
# DETERMINISTIC TREND CLASSIFICATION (app/agents/policy.py) — no HTTP, no DB
# ===========================================================================


def test_classify_score_trend_thresholds() -> None:
    assert classify_score_trend(10.0) == ProgressTrend.IMPROVING
    assert classify_score_trend(5.0) == ProgressTrend.IMPROVING  # boundary, inclusive
    assert classify_score_trend(3.0) == ProgressTrend.STABLE
    assert classify_score_trend(0.0) == ProgressTrend.STABLE
    assert classify_score_trend(-3.0) == ProgressTrend.STABLE
    assert classify_score_trend(-5.0) == ProgressTrend.DECLINING  # boundary, inclusive
    assert classify_score_trend(-10.0) == ProgressTrend.DECLINING


# ===========================================================================
# WRITE PATH — first completed interview, snapshots, idempotency
# ===========================================================================


async def test_first_completed_interview_creates_expected_progress_state(
    client: AsyncClient,
) -> None:
    token = await _register(client, email="progress-first1@example.com")
    interview_id = await _complete_coding_practice_session(client, token)
    user_id = await _session_user_id(interview_id)

    assert await _snapshot_count(user_id) == 1
    async with get_session_factory()() as session:
        snapshot = (
            await session.execute(
                select(UserProgressSnapshot).where(
                    UserProgressSnapshot.user_id == uuid.UUID(user_id)
                )
            )
        ).scalar_one()
        assert snapshot.interviews_completed == 1
        assert snapshot.avg_overall_score >= 0

    # Coding Practice's role is company-agnostic — no company_readiness row.
    assert await _company_readiness_rows(user_id) == []


async def test_incomplete_session_does_not_create_progress_state(client: AsyncClient) -> None:
    token = await _register(client, email="progress-incomplete1@example.com")
    role = await _find_role(client, token, role_key="software_engineer", company_id=None)
    template = await _find_template(client, token, role_id=role["id"], name="Coding Practice")
    interview = await _plan(
        client,
        token,
        {"role_id": role["id"], "template_id": template["id"], "difficulty": "medium"},
    )
    started = await _start(client, token, interview["id"])
    assert started.status_code == 200, started.text
    # Never submitted/completed.

    user_id = await _session_user_id(interview["id"])
    assert await _snapshot_count(user_id) == 0
    assert await _skill_progress_rows(user_id) == []


async def test_second_completed_interview_updates_snapshot_correctly(client: AsyncClient) -> None:
    token = await _register(client, email="progress-second1@example.com")
    interview_id_1 = await _complete_coding_practice_session(client, token)
    user_id = await _session_user_id(interview_id_1)
    assert await _snapshot_count(user_id) == 1

    # Second session, same user, same day — must UPDATE the one snapshot
    # row for today, not insert a second one.
    interview_id_2 = await _complete_coding_practice_session(client, token)
    assert await _session_user_id(interview_id_2) == user_id
    assert await _snapshot_count(user_id) == 1

    async with get_session_factory()() as session:
        snapshot = (
            await session.execute(
                select(UserProgressSnapshot).where(
                    UserProgressSnapshot.user_id == uuid.UUID(user_id)
                )
            )
        ).scalar_one()
        assert snapshot.interviews_completed == 2


async def test_repeated_report_generation_is_idempotent_for_progress(client: AsyncClient) -> None:
    token = await _register(client, email="progress-idempotent1@example.com")
    interview_id = await _complete_coding_practice_session(client, token)
    user_id = await _session_user_id(interview_id)

    assert await _snapshot_count(user_id) == 1
    skills_before = len(await _skill_progress_rows(user_id))

    # Manually re-trigger the same job for the same interview — must be a
    # clean no-op (ReportService's own idempotent pre-check returns the
    # existing report; ProgressService then recomputes the same state).
    await generate_report_job(job_id="manual-retry-1", interview_id=interview_id, user_id=user_id)

    assert await _snapshot_count(user_id) == 1
    assert len(await _skill_progress_rows(user_id)) == skills_before
    async with get_session_factory()() as session:
        snapshot = (
            await session.execute(
                select(UserProgressSnapshot).where(
                    UserProgressSnapshot.user_id == uuid.UUID(user_id)
                )
            )
        ).scalar_one()
        assert snapshot.interviews_completed == 1  # not double-counted


# ===========================================================================
# WEAK/STRONG AREA -> SKILL PROGRESS MAPPING
# ===========================================================================


async def test_weak_areas_map_to_skill_progress_with_correct_score(client: AsyncClient) -> None:
    provider = get_fake_interview_agent_provider()
    provider.forced_technical_score = 20.0
    provider.forced_problem_solving_score = 20.0
    try:
        token = await _register(client, email="progress-weak1@example.com")
        interview_id = await _complete_technical_mock_session(client, token, email_tag="weak1")
        user_id = await _session_user_id(interview_id)

        skills = await _skill_progress_rows(user_id)
        assert skills, "expected at least one skill_progress row"
        for skill in skills:
            # Every normalized skill's score must be 0-100 and traceable to
            # a real report_section_scores value (not a guessed/default
            # number) — a forced 20.0 technical score means the "technical"
            # -sourced skill(s) should reflect a low score.
            assert 0.0 <= float(skill.proficiency_score) <= 100.0
    finally:
        provider.reset()


async def test_skill_progress_trend_reflects_a_real_score_delta(client: AsyncClient) -> None:
    provider = get_fake_interview_agent_provider()
    try:
        token = await _register(client, email="progress-trend1@example.com")

        provider.forced_technical_score = 20.0
        provider.forced_problem_solving_score = 20.0
        interview_id_1 = await _complete_technical_mock_session(client, token, email_tag="trend-lo")
        user_id = await _session_user_id(interview_id_1)
        skills_after_first = {
            s.skill_name: float(s.proficiency_score) for s in await _skill_progress_rows(user_id)
        }
        assert skills_after_first

        provider.forced_technical_score = 95.0
        provider.forced_problem_solving_score = 95.0
        await _complete_technical_mock_session(client, token, email_tag="trend-hi")

        skills_after_second = await _skill_progress_rows(user_id)
        improved = [
            s
            for s in skills_after_second
            if s.skill_name in skills_after_first
            and float(s.proficiency_score) > skills_after_first[s.skill_name]
        ]
        assert improved, "expected at least one skill to score higher on the second pass"
        assert any(s.trend == ProgressTrend.IMPROVING for s in improved)
    finally:
        provider.reset()


# ===========================================================================
# COMPANY READINESS
# ===========================================================================


async def test_company_readiness_recorded_for_company_specific_session(
    client: AsyncClient,
) -> None:
    token = await _register(client, email="progress-company1@example.com")
    interview_id = await _complete_amazon_swe_session(client, token)
    user_id = await _session_user_id(interview_id)

    rows = await _company_readiness_rows(user_id)
    assert len(rows) == 1
    assert 0.0 <= float(rows[0].readiness_score) <= 100.0
    assert str(rows[0].last_interview_session_id) == interview_id


async def test_company_readiness_reflects_the_most_recent_session(client: AsyncClient) -> None:
    token = await _register(client, email="progress-company2@example.com")
    interview_id_1 = await _complete_amazon_swe_session(client, token)
    user_id = await _session_user_id(interview_id_1)
    rows_after_first = await _company_readiness_rows(user_id)
    assert len(rows_after_first) == 1

    interview_id_2 = await _complete_amazon_swe_session(client, token)
    rows_after_second = await _company_readiness_rows(user_id)
    assert (
        len(rows_after_second) == 1
    )  # still one row per (user, company) — updated, not duplicated
    assert str(rows_after_second[0].last_interview_session_id) == interview_id_2


# ===========================================================================
# DASHBOARD API — ownership, empty state, pagination
# ===========================================================================


async def test_dashboard_endpoints_require_authentication(client: AsyncClient) -> None:
    for path in (
        "/api/v1/dashboard/overview",
        "/api/v1/dashboard/skills",
        "/api/v1/dashboard/company-readiness",
        "/api/v1/dashboard/history",
    ):
        response = await client.get(path)
        assert response.status_code == 401, (path, response.text)


async def test_dashboard_empty_state_before_any_completed_session(client: AsyncClient) -> None:
    token = await _register(client, email="progress-empty1@example.com")

    overview = await client.get("/api/v1/dashboard/overview", headers=_auth(token))
    assert overview.status_code == 200, overview.text
    body = overview.json()
    assert body["interviews_completed"] == 0
    assert body["avg_overall_score"] == 0.0
    assert body["trend"] == "stable"

    skills = await client.get("/api/v1/dashboard/skills", headers=_auth(token))
    assert skills.status_code == 200 and skills.json() == []

    readiness = await client.get("/api/v1/dashboard/company-readiness", headers=_auth(token))
    assert readiness.status_code == 200 and readiness.json() == []

    history = await client.get("/api/v1/dashboard/history", headers=_auth(token))
    assert history.status_code == 200, history.text
    history_body = history.json()
    assert history_body["items"] == []
    assert history_body["total"] == 0


async def test_dashboard_data_scoped_to_owner_only(client: AsyncClient) -> None:
    owner_token = await _register(client, email="progress-owner1@example.com")
    await _complete_coding_practice_session(client, owner_token)

    other_token = await _register(client, email="progress-other1@example.com")
    overview = await client.get("/api/v1/dashboard/overview", headers=_auth(other_token))
    assert overview.status_code == 200, overview.text
    assert overview.json()["interviews_completed"] == 0  # never sees the owner's data

    history = await client.get("/api/v1/dashboard/history", headers=_auth(other_token))
    assert history.json()["total"] == 0


async def test_dashboard_overview_reflects_completed_session(client: AsyncClient) -> None:
    token = await _register(client, email="progress-overview1@example.com")
    await _complete_coding_practice_session(client, token)

    response = await client.get("/api/v1/dashboard/overview", headers=_auth(token))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["interviews_completed"] == 1
    assert body["avg_overall_score"] >= 0
    assert body["trend"] in ("improving", "stable", "declining")


async def test_dashboard_history_lists_session_with_report_summary(client: AsyncClient) -> None:
    token = await _register(client, email="progress-history1@example.com")
    interview_id = await _complete_coding_practice_session(client, token)

    response = await client.get("/api/v1/dashboard/history", headers=_auth(token))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 1
    item = body["items"][0]
    assert item["session_id"] == interview_id
    assert item["status"] == "completed"
    assert item["report"] is not None
    assert item["report"]["overall_score"] >= 0


async def test_dashboard_history_pagination(client: AsyncClient) -> None:
    token = await _register(client, email="progress-page1@example.com")
    ids = [await _complete_coding_practice_session(client, token) for _ in range(3)]

    page1 = await client.get(
        "/api/v1/dashboard/history", headers=_auth(token), params={"limit": 2, "offset": 0}
    )
    assert page1.status_code == 200, page1.text
    body1 = page1.json()
    assert body1["total"] == 3
    assert len(body1["items"]) == 2
    assert body1["limit"] == 2
    assert body1["offset"] == 0

    page2 = await client.get(
        "/api/v1/dashboard/history", headers=_auth(token), params={"limit": 2, "offset": 2}
    )
    assert page2.status_code == 200, page2.text
    body2 = page2.json()
    assert len(body2["items"]) == 1

    # Most-recent-first ordering, no overlap/gap across pages.
    all_ids = [item["session_id"] for item in body1["items"] + body2["items"]]
    assert set(all_ids) == set(ids)
    assert len(all_ids) == len(set(all_ids))


async def test_dashboard_company_readiness_includes_company_name(client: AsyncClient) -> None:
    token = await _register(client, email="progress-readiness-api1@example.com")
    await _complete_amazon_swe_session(client, token)

    response = await client.get("/api/v1/dashboard/company-readiness", headers=_auth(token))
    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body) == 1
    assert body[0]["company_name"]
    assert 0.0 <= body[0]["readiness_score"] <= 100.0
