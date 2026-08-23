"""Module 7 (Report Generator & Learning Roadmap) tests.

Uses FakeReportGenerationProvider (deterministic, no network) —
REPORT_GENERATION_PROVIDER=fake in .env.test. Never depends on live
Gemini for this automated suite (module §24), same convention
test_coding_round.py's own docstring establishes for
CODE_EVALUATION_PROVIDER.

Every completed-session test drives either "Coding Practice" (Module 6's
own single-coding-round template) or "Behavioral Prep" (introduction +
behavioral x2, text-only) through to SessionStatus.COMPLETED — the
shortest paths to a real, evaluated, completed session, already
established by tests/test_coding_round.py and
tests/test_interview_execution.py respectively. Helpers below are
deliberately duplicated rather than imported, mirroring this codebase's
existing per-file-independent-helpers convention (test_coding_round.py's
own docstring: "mirrors tests/test_interview_execution.py's conventions").

Under httpx's ASGITransport, FastAPI's BackgroundTasks — and therefore
both of generate_report_job's trigger paths (app/api/v1/interviews.py's
enqueue, app/jobs/coding_execution.py's direct await) — execute
synchronously within the same request/response cycle
(test_coding_round.py's own documented fact, restated here): a
session-completing POST's response already reflects report generation
having finished (successfully or, if the fake provider was told to fail,
having failed and logged), no polling needed.
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.agents.checkpointer import get_checkpointer
from app.agents.policy import (
    classify_weak_area_severity,
    compute_overall_score,
    compute_round_composite,
    compute_section_score,
)
from app.db.session import get_session_factory
from app.jobs.report_generation import generate_report_job
from app.models.enums import Severity
from app.models.interview import InterviewSession
from app.models.report import InterviewReport
from app.services.interview_intelligence.fake_provider import get_fake_interview_agent_provider
from app.services.report_generation.fake_provider import get_fake_report_generation_provider

VALID_PASSWORD = "correct-horse-42"


@pytest.fixture(autouse=True)
async def _ensure_checkpoint_tables() -> None:
    """Same requirement as test_interview_execution.py's own fixture of
    this name — any test that drives /start or /answers needs LangGraph's
    checkpoint tables, which httpx's ASGITransport never creates via a
    lifespan event.
    """
    async with get_checkpointer() as checkpointer:
        await checkpointer.setup()


# --- helpers (mirrors tests/test_coding_round.py's/test_interview_execution.py's
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
    raise AssertionError(f"role_key={role_key} not found")


async def _find_template(client: AsyncClient, token: str, *, role_id: str, name: str) -> dict:
    response = await client.get(f"/api/v1/roles/{role_id}/templates", headers=_auth(token))
    assert response.status_code == 200, response.text
    for t in response.json():
        if t["name"] == name:
            return t
    raise AssertionError(f"template name={name!r} not found")


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


async def _plan_coding_practice(client: AsyncClient, token: str) -> dict:
    role = await _find_role(client, token, role_key="software_engineer", company_id=None)
    template = await _find_template(client, token, role_id=role["id"], name="Coding Practice")
    return await _plan(
        client,
        token,
        {"role_id": role["id"], "template_id": template["id"], "difficulty": "medium"},
    )


async def _plan_behavioral_prep(client: AsyncClient, token: str) -> dict:
    role = await _find_role(client, token, role_key="software_engineer", company_id=None)
    template = await _find_template(client, token, role_id=role["id"], name="Behavioral Prep")
    return await _plan(
        client,
        token,
        {"role_id": role["id"], "template_id": template["id"], "difficulty": "medium"},
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


async def _complete_coding_session(client: AsyncClient, token: str) -> str:
    """Registers a Coding Practice interview (one coding round) and
    submits a correct final solution — the shortest path to
    SessionStatus.COMPLETED with a real coding evaluation. Returns
    interview_id.
    """
    interview = await _plan_coding_practice(client, token)
    started = await _start(client, token, interview["id"])
    assert started.status_code == 200, started.text
    assert started.json()["question"]["round_type"] == "coding"
    question_id = started.json()["question"]["id"]

    response = await _submit_code(
        client,
        token,
        interview["id"],
        question_id,
        source_code="# CORRECT_SOLUTION",
        is_final=True,
    )
    assert response.status_code == 202, response.text
    return interview["id"]


async def _complete_text_only_session(client: AsyncClient, token: str) -> str:
    """Registers a Behavioral Prep interview (introduction + behavioral
    x2, text-only) and answers through to SessionStatus.COMPLETED.
    """
    interview = await _plan_behavioral_prep(client, token)
    started = await _start(client, token, interview["id"])
    assert started.status_code == 200, started.text
    question_id = started.json()["question"]["id"]

    provider = get_fake_interview_agent_provider()
    provider.forced_follow_up_worthy = False  # exercise pure round progression

    response = None
    for _ in range(3):
        response = await _answer(client, token, interview["id"], question_id, "a reasonable answer")
        assert response.status_code == 200, response.text
        if response.json()["next"]["type"] == "session_complete":
            break
        question_id = response.json()["next"]["question"]["id"]
    assert response.json()["next"]["type"] == "session_complete", response.text
    return interview["id"]


async def _get_report(client: AsyncClient, token: str, interview_id: str):
    return await client.get(
        f"/api/v1/interview-sessions/{interview_id}/report", headers=_auth(token)
    )


async def _session_user_id(interview_id: str) -> str:
    async with get_session_factory()() as session:
        interview = await session.get(InterviewSession, uuid.UUID(interview_id))
        return str(interview.user_id)


async def _complete_technical_mock_session_with_low_scores(client: AsyncClient, token: str) -> str:
    """ "Technical Mock" (introduction -> technical x3 -> coding, role_key
    backend_engineer) driven to full completion, with technical_score/
    problem_solving_score forced low so the report has a guaranteed weak
    area to test against — deterministic rather than incidental. Caller
    is responsible for resetting the forced_* fields afterward.
    """
    interview_provider = get_fake_interview_agent_provider()
    interview_provider.forced_technical_score = 20.0
    interview_provider.forced_problem_solving_score = 20.0
    interview_provider.forced_follow_up_worthy = False

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

    # introduction (1) + technical (3) = 4 answers exhausts both, landing
    # on the coding round's question (mirrors test_interview_execution.py's
    # test_coding_round_in_mixed_plan_is_reached_not_skipped).
    response = None
    for _ in range(4):
        response = await _answer(client, token, interview["id"], question_id, "a weak answer")
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


# ===========================================================================
# DETERMINISTIC SCORING (app/agents/policy.py) — no HTTP, no DB
# ===========================================================================


def test_compute_section_score_is_a_plain_average() -> None:
    assert compute_section_score([80.0, 90.0, 70.0]) == 80.0


def test_compute_round_composite_averages_every_dimension_together() -> None:
    assert compute_round_composite([80.0, 70.0, 90.0, 60.0]) == 75.0


def test_compute_overall_score_weights_by_round_weight() -> None:
    # round A: composite=80, weight=2; round B: composite=60, weight=1
    result = compute_overall_score([(80.0, 2.0), (60.0, 1.0)])
    assert result == round((80.0 * 2.0 + 60.0 * 1.0) / 3.0, 2)


def test_compute_overall_score_all_zero_weight_returns_zero() -> None:
    assert compute_overall_score([(80.0, 0.0), (60.0, 0.0)]) == 0.0


def test_classify_weak_area_severity_thresholds() -> None:
    assert classify_weak_area_severity(30.0) == Severity.HIGH
    assert classify_weak_area_severity(40.0) == Severity.HIGH  # boundary, inclusive
    assert classify_weak_area_severity(50.0) == Severity.MEDIUM
    assert classify_weak_area_severity(65.0) == Severity.MEDIUM  # boundary, inclusive
    assert classify_weak_area_severity(66.0) == Severity.LOW
    assert classify_weak_area_severity(95.0) == Severity.LOW


# ===========================================================================
# FAKE PROVIDER BEHAVIOR
# ===========================================================================


async def test_fake_report_generation_provider_tracks_calls_and_resets() -> None:
    fake = get_fake_report_generation_provider()
    fake.reset()
    await fake.generate(
        role_title="Software Engineer",
        company_name=None,
        section_scores={"technical": 80.0},
        overall_score=80.0,
        evidence=[],
    )
    assert fake.calls == ["generate"]
    fake.reset()
    assert fake.calls == []


async def test_fake_report_generation_provider_fail_flag_raises() -> None:
    from app.services.report_generation.provider import ReportGenerationProviderError

    fake = get_fake_report_generation_provider()
    fake.fail = True
    try:
        with pytest.raises(ReportGenerationProviderError):
            await fake.generate(
                role_title="x", company_name=None, section_scores={}, overall_score=0.0, evidence=[]
            )
    finally:
        fake.reset()


async def test_fake_report_generation_provider_timeout_flag_raises() -> None:
    from app.services.report_generation.provider import ReportGenerationTimeoutError

    fake = get_fake_report_generation_provider()
    fake.timeout = True
    try:
        with pytest.raises(ReportGenerationTimeoutError):
            await fake.generate(
                role_title="x", company_name=None, section_scores={}, overall_score=0.0, evidence=[]
            )
    finally:
        fake.reset()


# ===========================================================================
# COMPLETED-SESSION INTEGRATION
# ===========================================================================


async def test_completed_coding_session_generates_a_report(client: AsyncClient) -> None:
    token = await _register(client, email="report-coding1@example.com")
    interview_id = await _complete_coding_session(client, token)

    response = await _get_report(client, token, interview_id)
    assert response.status_code == 200, response.text
    body = response.json()
    assert "coding" in body["sections"]
    assert body["overall"]["score"] > 0


async def test_completed_text_only_session_has_no_coding_section(client: AsyncClient) -> None:
    token = await _register(client, email="report-text1@example.com")
    interview_id = await _complete_text_only_session(client, token)

    response = await _get_report(client, token, interview_id)
    assert response.status_code == 200, response.text
    body = response.json()
    # "coding" is the only section that's ever absent — the Evaluation
    # Agent scores technical/problem_solving/communication/confidence for
    # EVERY text answer regardless of the round's own topic (Architecture.md
    # §5.1's roster), so a text-only session still has all four text
    # sections; only a session with no coding round has no CodingEvaluation
    # rows to produce a "coding" section from at all.
    assert "coding" not in body["sections"]
    assert "technical" in body["sections"]
    assert "problem_solving" in body["sections"]
    assert "communication" in body["sections"]
    assert "confidence" in body["sections"]


async def test_every_report_score_has_a_paired_explanation(client: AsyncClient) -> None:
    token = await _register(client, email="report-explain1@example.com")
    interview_id = await _complete_coding_session(client, token)

    body = (await _get_report(client, token, interview_id)).json()
    assert body["overall"]["explanation"]
    for section in body["sections"].values():
        assert section["score"] is not None
        assert section["explanation"]


async def test_weak_area_and_roadmap_generated_from_a_low_score(client: AsyncClient) -> None:
    """FakeReportGenerationProvider flags any section scoring below 65 as
    a weak area (and one roadmap item per weak area) — forcing a low
    technical_score deterministically exercises that path instead of
    depending on incidental scoring.
    """
    provider = get_fake_interview_agent_provider()
    try:
        token = await _register(client, email="report-weak1@example.com")
        interview_id = await _complete_technical_mock_session_with_low_scores(client, token)

        report_response = await _get_report(client, token, interview_id)
        assert report_response.status_code == 200, report_response.text
        body = report_response.json()
        assert body["weak_areas"], body
        weak = body["weak_areas"][0]
        assert weak["topic"]
        assert weak["evidence"]
        assert weak["severity"] in (Severity.HIGH.value, Severity.MEDIUM.value)
    finally:
        provider.reset()


# ===========================================================================
# REPORT API
# ===========================================================================


async def test_report_not_visible_before_generation(client: AsyncClient) -> None:
    token = await _register(client, email="report-early1@example.com")
    interview = await _plan_coding_practice(client, token)
    started = await _start(client, token, interview["id"])
    assert started.status_code == 200, started.text

    response = await _get_report(client, token, interview["id"])
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "REPORT_NOT_YET_AVAILABLE"


async def test_report_not_visible_to_a_different_candidate(client: AsyncClient) -> None:
    owner_token = await _register(client, email="report-owner1@example.com")
    interview_id = await _complete_coding_session(client, owner_token)

    intruder_token = await _register(client, email="report-intruder1@example.com")
    response = await _get_report(client, intruder_token, interview_id)
    assert response.status_code == 404


async def test_get_roadmap_for_report(client: AsyncClient) -> None:
    token = await _register(client, email="report-roadmap1@example.com")
    interview_id = await _complete_coding_session(client, token)
    report_id = (await _get_report(client, token, interview_id)).json()["id"]

    response = await client.get(f"/api/v1/reports/{report_id}/roadmap", headers=_auth(token))
    assert response.status_code == 200, response.text
    body = response.json()
    assert "items" in body


async def test_roadmap_item_patch_updates_completion_and_is_idempotent(
    client: AsyncClient,
) -> None:
    provider = get_fake_interview_agent_provider()
    try:
        token = await _register(client, email="report-patch1@example.com")
        interview_id = await _complete_technical_mock_session_with_low_scores(client, token)

        report_body = (await _get_report(client, token, interview_id)).json()
        roadmap_body = (
            await client.get(f"/api/v1/reports/{report_body['id']}/roadmap", headers=_auth(token))
        ).json()
        assert roadmap_body["items"], roadmap_body
        item_id = roadmap_body["items"][0]["id"]
        assert roadmap_body["items"][0]["is_completed"] is False

        patch1 = await client.patch(
            f"/api/v1/roadmap-items/{item_id}", headers=_auth(token), json={"is_completed": True}
        )
        assert patch1.status_code == 200, patch1.text
        assert patch1.json()["is_completed"] is True

        # Idempotent — patching the same value again is a clean no-op.
        patch2 = await client.patch(
            f"/api/v1/roadmap-items/{item_id}", headers=_auth(token), json={"is_completed": True}
        )
        assert patch2.status_code == 200, patch2.text
        assert patch2.json()["is_completed"] is True
    finally:
        provider.reset()


async def test_roadmap_item_patch_rejected_for_a_different_candidate(
    client: AsyncClient,
) -> None:
    provider = get_fake_interview_agent_provider()
    try:
        owner_token = await _register(client, email="report-patch-owner1@example.com")
        interview_id = await _complete_technical_mock_session_with_low_scores(client, owner_token)

        report_body = (await _get_report(client, owner_token, interview_id)).json()
        roadmap_body = (
            await client.get(
                f"/api/v1/reports/{report_body['id']}/roadmap", headers=_auth(owner_token)
            )
        ).json()
        item_id = roadmap_body["items"][0]["id"]

        intruder_token = await _register(client, email="report-patch-intruder1@example.com")
        response = await client.patch(
            f"/api/v1/roadmap-items/{item_id}",
            headers=_auth(intruder_token),
            json={"is_completed": True},
        )
        assert response.status_code == 404
    finally:
        provider.reset()


# ===========================================================================
# IDEMPOTENCY / FAILURE-RETRY OF THE BACKGROUND JOB
# ===========================================================================


async def test_repeated_report_generation_creates_no_duplicate(client: AsyncClient) -> None:
    token = await _register(client, email="report-idempotent1@example.com")
    interview_id = await _complete_coding_session(client, token)

    async def _report_count() -> int:
        async with get_session_factory()() as session:
            result = await session.execute(
                select(InterviewReport).where(InterviewReport.session_id == uuid.UUID(interview_id))
            )
            return len(result.scalars().all())

    assert await _report_count() == 1

    user_id = await _session_user_id(interview_id)
    await generate_report_job(job_id="manual-retry-1", interview_id=interview_id, user_id=user_id)

    assert await _report_count() == 1


async def test_failed_generation_leaves_no_report_then_succeeds_on_retry(
    client: AsyncClient,
) -> None:
    fake = get_fake_report_generation_provider()
    fake.fail = True
    try:
        token = await _register(client, email="report-retry1@example.com")
        interview_id = await _complete_coding_session(client, token)

        async with get_session_factory()() as session:
            result = await session.execute(
                select(InterviewReport).where(InterviewReport.session_id == uuid.UUID(interview_id))
            )
            assert result.scalar_one_or_none() is None

        response = await _get_report(client, token, interview_id)
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "REPORT_NOT_YET_AVAILABLE"

        fake.fail = False
        user_id = await _session_user_id(interview_id)
        await generate_report_job(
            job_id="manual-retry-2", interview_id=interview_id, user_id=user_id
        )

        response2 = await _get_report(client, token, interview_id)
        assert response2.status_code == 200, response2.text
    finally:
        fake.reset()
