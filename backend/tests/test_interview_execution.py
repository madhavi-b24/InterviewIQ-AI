"""Module 5 (LangGraph Adaptive Interview Engine) tests.

Uses FakeInterviewAgentProvider (deterministic, no network) —
INTERVIEW_ENGINE_PROVIDER=fake in .env.test. Never depends on live Gemini
for the automated suite (module §24). Catalog data is seeded idempotently
by conftest.py's autouse `_seed_catalog` fixture, same as
test_interview_planning.py.
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.agents.checkpointer import get_checkpointer
from app.agents.policy import MAX_FOLLOW_UPS_PER_QUESTION
from app.db.session import get_session_factory
from app.models.interview import Answer, InterviewRound
from app.services.interview_intelligence.fake_provider import get_fake_interview_agent_provider
from tests.pdf_fixtures import fictional_resume_pdf

VALID_PASSWORD = "correct-horse-42"


@pytest.fixture(autouse=True)
async def _ensure_checkpoint_tables() -> None:
    """Module 5's LangGraph checkpoint tables live outside Alembic's schema
    (app/agents/checkpointer.py) and are normally created by
    app/main.py's lifespan — which httpx's ASGITransport (used by the
    `client` fixture) never triggers, since it doesn't run ASGI lifespan
    events. `.setup()` is idempotent, so calling it before every test in
    this file is safe; not session-scoped for the same
    per-test-event-loop-fragility reason conftest.py's `_seed_catalog`
    documents.
    """
    async with get_checkpointer() as checkpointer:
        await checkpointer.setup()


# Fake-provider reset between tests is handled globally by
# conftest.py's `_clean_state_between_tests` (mirrors
# get_fake_resume_intelligence_provider().reset() there).


# --- helpers (mirrors tests/test_interview_planning.py's conventions) ------


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


async def _roles(client: AsyncClient, token: str) -> list[dict]:
    response = await client.get("/api/v1/roles", headers=_auth(token))
    assert response.status_code == 200, response.text
    return response.json()


async def _find_role(client: AsyncClient, token: str, *, role_key: str, company_id=None) -> dict:
    roles = await _roles(client, token)
    for r in roles:
        if r["role_key"] == role_key and r["company_id"] == company_id:
            return r
    raise AssertionError(f"role_key={role_key} not found in {roles}")


async def _templates_for_role(
    client: AsyncClient, token: str, role_id: str, **params
) -> list[dict]:
    query = {k: v for k, v in params.items() if v is not None}
    response = await client.get(
        f"/api/v1/roles/{role_id}/templates", headers=_auth(token), params=query
    )
    assert response.status_code == 200, response.text
    return response.json()


async def _find_template(
    client: AsyncClient, token: str, *, role_id: str, name: str, company_id=None
) -> dict:
    templates = await _templates_for_role(client, token, role_id, company_id=company_id)
    for t in templates:
        if t["name"] == name:
            return t
    raise AssertionError(f"template name={name!r} not found in {templates}")


async def _upload_and_analyze(
    client: AsyncClient, token: str, *, role_key: str = "backend_engineer"
) -> str:
    response = await client.post(
        "/api/v1/resumes",
        headers=_auth(token),
        files={"file": ("resume.pdf", fictional_resume_pdf(), "application/pdf")},
    )
    assert response.status_code == 201, response.text
    resume_id = response.json()["id"]
    detail = await client.get(f"/api/v1/resumes/{resume_id}", headers=_auth(token))
    assert detail.json()["parsed_status"] == "done", detail.text
    gap = await client.post(
        f"/api/v1/resumes/{resume_id}/gap-analysis",
        headers=_auth(token),
        json={"role_key": role_key},
    )
    assert gap.status_code == 200, gap.text
    return resume_id


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


async def _current_turn(client: AsyncClient, token: str, interview_id: str):
    return await client.get(
        f"/api/v1/interview-sessions/{interview_id}/current-turn", headers=_auth(token)
    )


async def _abandon(client: AsyncClient, token: str, interview_id: str):
    return await client.post(
        f"/api/v1/interview-sessions/{interview_id}/abandon", headers=_auth(token)
    )


async def _plan_behavioral_prep(
    client: AsyncClient, token: str, *, difficulty: str = "medium"
) -> dict:
    role = await _find_role(client, token, role_key="software_engineer", company_id=None)
    template = await _find_template(client, token, role_id=role["id"], name="Behavioral Prep")
    return await _plan(
        client,
        token,
        {"role_id": role["id"], "template_id": template["id"], "difficulty": difficulty},
    )


# ===========================================================================
# START
# ===========================================================================


async def test_planned_interview_starts(client: AsyncClient) -> None:
    token = await _register(client, email="start1@example.com")
    interview = await _plan_behavioral_prep(client, token)

    response = await _start(client, token, interview["id"])
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "in_progress"
    assert body["current_round"] == "introduction"
    assert body["current_difficulty"] == "medium"
    assert body["question"]["question_text"]
    assert body["question"]["parent_question_id"] is None


async def test_already_started_interview_cannot_start_twice(client: AsyncClient) -> None:
    token = await _register(client, email="start2@example.com")
    interview = await _plan_behavioral_prep(client, token)
    first = await _start(client, token, interview["id"])
    assert first.status_code == 200

    second = await _start(client, token, interview["id"])
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "INTERVIEW_ALREADY_STARTED"


async def test_unauthorized_user_cannot_start_others_interview(client: AsyncClient) -> None:
    owner_token = await _register(client, email="start3-owner@example.com")
    interview = await _plan_behavioral_prep(client, owner_token)

    attacker_token = await _register(client, email="start3-attacker@example.com")
    response = await _start(client, attacker_token, interview["id"])
    assert response.status_code == 404


async def test_all_coding_plan_starts_with_a_coding_question(client: AsyncClient) -> None:
    """Module 6 — supersedes Module 5's test_all_coding_plan_rejected_at_start:
    a plan whose only round is `coding` used to be rejected at start
    (ALL_ROUNDS_UNSUPPORTED, a Module 5 placeholder — coding execution
    wasn't built yet). Coding rounds are real now, so this plan starts
    successfully and its first (only) question is a coding question. Full
    Run/Submit-through-completion coverage lives in tests/test_coding_round.py;
    this test only proves start_interview's own round-type routing decision.
    """
    token = await _register(client, email="start4@example.com")
    role = await _find_role(client, token, role_key="software_engineer", company_id=None)
    template = await _find_template(client, token, role_id=role["id"], name="Coding Practice")
    interview = await _plan(
        client,
        token,
        {"role_id": role["id"], "template_id": template["id"], "difficulty": "medium"},
    )

    response = await _start(client, token, interview["id"])
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["current_round"] == "coding"
    assert body["question"]["round_type"] == "coding"
    assert body["question"]["parent_question_id"] is None
    assert body["question"]["question_text"]  # the problem's description, never blank


# ===========================================================================
# ANSWERS
# ===========================================================================


async def test_answer_is_persisted_and_evaluated(client: AsyncClient) -> None:
    token = await _register(client, email="answer1@example.com")
    interview = await _plan_behavioral_prep(client, token)
    started = await _start(client, token, interview["id"])
    question_id = started.json()["question"]["id"]

    response = await _answer(
        client, token, interview["id"], question_id, "My name is Alex and I love backend systems."
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body["evaluation"].keys()) >= {
        "technical",
        "problem_solving",
        "communication",
        "confidence",
        "difficulty_signal",
    }
    assert body["next"]["type"] == "question"
    assert body["next"]["question"]["question_text"]

    async with get_session_factory()() as session:
        result = await session.execute(
            select(Answer).where(Answer.question_id == uuid.UUID(question_id))
        )
        answers = result.scalars().all()
        assert len(answers) == 1


async def test_current_difficulty_updates_after_strong_answer(client: AsyncClient) -> None:
    token = await _register(client, email="answer2@example.com")
    interview = await _plan_behavioral_prep(client, token)
    started = await _start(client, token, interview["id"])
    question_id = started.json()["question"]["id"]

    provider = get_fake_interview_agent_provider()
    provider.forced_technical_score = 95
    provider.forced_problem_solving_score = 95
    provider.forced_follow_up_worthy = False

    response = await _answer(
        client, token, interview["id"], question_id, "A strong detailed answer."
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["previous_difficulty"] == "medium"
    assert body["current_difficulty"] == "hard"
    assert body["evaluation"]["difficulty_signal"] == "increase"


async def test_duplicate_answer_retry_is_idempotent(client: AsyncClient) -> None:
    token = await _register(client, email="answer3@example.com")
    interview = await _plan_behavioral_prep(client, token)
    started = await _start(client, token, interview["id"])
    question_id = started.json()["question"]["id"]

    first = await _answer(client, token, interview["id"], question_id, "First submission text.")
    assert first.status_code == 200, first.text

    second = await _answer(client, token, interview["id"], question_id, "First submission text.")
    assert second.status_code == 200, second.text
    assert first.json()["evaluation"] == second.json()["evaluation"]
    assert first.json()["next"] == second.json()["next"]

    async with get_session_factory()() as session:
        result = await session.execute(
            select(Answer).where(Answer.question_id == uuid.UUID(question_id))
        )
        assert len(result.scalars().all()) == 1

    # Only one evaluate_technical/evaluate_communication call pair should
    # have actually run — the second request replayed, it didn't re-call
    # the provider.
    provider = get_fake_interview_agent_provider()
    assert provider.calls.count("evaluate_technical") == 1


async def test_nonexistent_question_id_rejected(client: AsyncClient) -> None:
    token = await _register(client, email="answer4@example.com")
    interview = await _plan_behavioral_prep(client, token)
    await _start(client, token, interview["id"])

    response = await _answer(client, token, interview["id"], str(uuid.uuid4()), "irrelevant")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "QUESTION_NOT_FOUND"


async def test_resubmitting_different_text_for_answered_question_replays_original(
    client: AsyncClient,
) -> None:
    """Once a question has an Answer, that turn is immutable — a second
    submission (even with different text) never overwrites it; it always
    replays what was actually recorded. This is what makes the idempotency
    check safe against a retry whose text a proxy/client mutated in
    transit, not just byte-identical retries.
    """
    token = await _register(client, email="answer5@example.com")
    interview = await _plan_behavioral_prep(client, token)
    started = await _start(client, token, interview["id"])
    question_id = started.json()["question"]["id"]

    first = await _answer(client, token, interview["id"], question_id, "the real answer")
    assert first.status_code == 200, first.text

    resubmit = await _answer(
        client, token, interview["id"], question_id, "a completely different answer"
    )
    assert resubmit.status_code == 200, resubmit.text
    assert resubmit.json()["evaluation"] == first.json()["evaluation"]

    async with get_session_factory()() as session:
        result = await session.execute(
            select(Answer).where(Answer.question_id == uuid.UUID(question_id))
        )
        answers = result.scalars().all()
        assert len(answers) == 1
        assert answers[0].answer_text == "the real answer"  # never overwritten


async def test_question_id_from_another_interview_rejected_as_stale(client: AsyncClient) -> None:
    token = await _register(client, email="answer6@example.com")
    interview_a = await _plan_behavioral_prep(client, token)
    await _start(client, token, interview_a["id"])

    interview_b = await _plan_behavioral_prep(client, token)
    started_b = await _start(client, token, interview_b["id"])
    question_from_b = started_b.json()["question"]["id"]

    response = await _answer(client, token, interview_a["id"], question_from_b, "wrong interview")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "STALE_QUESTION_ID"


# ===========================================================================
# FOLLOW-UP
# ===========================================================================


async def test_follow_up_generated_when_flagged(client: AsyncClient) -> None:
    token = await _register(client, email="followup1@example.com")
    interview = await _plan_behavioral_prep(client, token)
    started = await _start(client, token, interview["id"])
    question_id = started.json()["question"]["id"]

    provider = get_fake_interview_agent_provider()
    provider.forced_follow_up_worthy = True

    response = await _answer(client, token, interview["id"], question_id, "A shallow answer.")
    assert response.status_code == 200, response.text
    next_question = response.json()["next"]["question"]
    assert next_question["parent_question_id"] == question_id


async def test_follow_up_limit_enforced_no_infinite_loop(client: AsyncClient) -> None:
    token = await _register(client, email="followup2@example.com")
    interview = await _plan_behavioral_prep(client, token)
    started = await _start(client, token, interview["id"])
    question_id = started.json()["question"]["id"]
    root_question_id = question_id

    provider = get_fake_interview_agent_provider()
    provider.forced_follow_up_worthy = True

    # Answer the root question and every follow-up up to the cap — every
    # one of these must be a follow-up (parent chain back to the root).
    for _ in range(MAX_FOLLOW_UPS_PER_QUESTION):
        response = await _answer(client, token, interview["id"], question_id, "Shallow every time.")
        assert response.status_code == 200, response.text
        next_question = response.json()["next"]["question"]
        assert next_question["parent_question_id"] is not None
        question_id = next_question["id"]

    # One more still-shallow answer must NOT produce yet another follow-up
    # — the cap forces the engine to move on despite follow_up_worthy still
    # being true.
    response = await _answer(client, token, interview["id"], question_id, "Still shallow.")
    assert response.status_code == 200, response.text
    next_question = response.json()["next"]["question"]
    assert next_question is not None
    assert next_question["id"] != root_question_id


# ===========================================================================
# DIFFICULTY
# ===========================================================================


async def test_weak_answer_decreases_difficulty(client: AsyncClient) -> None:
    token = await _register(client, email="difficulty1@example.com")
    interview = await _plan_behavioral_prep(client, token)
    started = await _start(client, token, interview["id"])
    question_id = started.json()["question"]["id"]

    provider = get_fake_interview_agent_provider()
    provider.forced_technical_score = 10
    provider.forced_problem_solving_score = 10
    provider.forced_follow_up_worthy = False

    response = await _answer(client, token, interview["id"], question_id, "weak")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["previous_difficulty"] == "medium"
    assert body["current_difficulty"] == "easy"
    assert body["evaluation"]["difficulty_signal"] == "decrease"


async def test_borderline_answer_maintains_difficulty_no_oscillation(client: AsyncClient) -> None:
    token = await _register(client, email="difficulty2@example.com")
    interview = await _plan_behavioral_prep(client, token)
    started = await _start(client, token, interview["id"])
    question_id = started.json()["question"]["id"]

    provider = get_fake_interview_agent_provider()
    provider.forced_technical_score = 60
    provider.forced_problem_solving_score = 60
    provider.forced_follow_up_worthy = False

    response = await _answer(client, token, interview["id"], question_id, "a middling answer")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["previous_difficulty"] == "medium"
    assert body["current_difficulty"] == "medium"
    assert body["evaluation"]["difficulty_signal"] == "maintain"


async def test_difficulty_clamped_at_hard(client: AsyncClient) -> None:
    token = await _register(client, email="difficulty3@example.com")
    interview = await _plan_behavioral_prep(client, token, difficulty="hard")
    started = await _start(client, token, interview["id"])
    question_id = started.json()["question"]["id"]

    provider = get_fake_interview_agent_provider()
    provider.forced_technical_score = 99
    provider.forced_problem_solving_score = 99
    provider.forced_follow_up_worthy = False

    response = await _answer(client, token, interview["id"], question_id, "excellent answer")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["previous_difficulty"] == "hard"
    assert body["current_difficulty"] == "hard"  # clamped, never overflows past hard


# ===========================================================================
# ROUNDS
# ===========================================================================


async def test_rounds_transition_in_order_and_reach_completed(client: AsyncClient) -> None:
    token = await _register(client, email="rounds1@example.com")
    interview = await _plan_behavioral_prep(client, token)
    started = await _start(client, token, interview["id"])
    assert started.json()["current_round"] == "introduction"
    question_id = started.json()["question"]["id"]

    provider = get_fake_interview_agent_provider()
    provider.forced_follow_up_worthy = False  # no follow-ups, exercise pure round progression

    # introduction (target 1) -> behavioral round begins
    r1 = await _answer(client, token, interview["id"], question_id, "intro answer")
    assert r1.status_code == 200, r1.text
    assert r1.json()["next"]["type"] == "question"
    q2 = r1.json()["next"]["question"]

    # behavioral answer 1/2
    r2 = await _answer(client, token, interview["id"], q2["id"], "behavioral answer one")
    assert r2.status_code == 200, r2.text
    assert r2.json()["next"]["type"] == "question"
    q3 = r2.json()["next"]["question"]

    # behavioral answer 2/2 -> Behavioral Prep has no round after this -> complete
    r3 = await _answer(client, token, interview["id"], q3["id"], "behavioral answer two")
    assert r3.status_code == 200, r3.text
    assert r3.json()["next"]["type"] == "session_complete"
    assert r3.json()["status"] == "completed"

    detail = await client.get(f"/api/v1/interview-sessions/{interview['id']}", headers=_auth(token))
    assert detail.json()["status"] == "completed"


async def test_coding_round_in_mixed_plan_is_reached_not_skipped(client: AsyncClient) -> None:
    """Module 6 — supersedes Module 5's test_coding_round_is_skipped_not_faked:
    "Technical Mock" is introduction -> technical(x3) -> coding. Answering
    through the first two rounds must land on a real coding QUESTION, not
    an immediate session_complete with the coding round silently marked
    SKIPPED (Module 5's placeholder behavior). Actually driving that
    coding question through Run/Submit to completion is
    tests/test_coding_round.py's job — this test only proves the round
    -transition routing decision.
    """
    token = await _register(client, email="rounds2@example.com")
    role = await _find_role(client, token, role_key="backend_engineer", company_id=None)
    template = await _find_template(client, token, role_id=role["id"], name="Technical Mock")
    interview = await _plan(
        client,
        token,
        {"role_id": role["id"], "template_id": template["id"], "difficulty": "medium"},
    )
    started = await _start(client, token, interview["id"])
    question_id = started.json()["question"]["id"]

    provider = get_fake_interview_agent_provider()
    provider.forced_follow_up_worthy = False

    # introduction (1) + technical (3) = 4 answers exhausts both non-coding
    # rounds; the 4th answer's `next` must be the coding round's question.
    response = None
    for _ in range(4):
        response = await _answer(client, token, interview["id"], question_id, "a reasonable answer")
        assert response.status_code == 200, response.text
        assert response.json()["next"]["type"] == "question"
        question_id = response.json()["next"]["question"]["id"]

    assert response.json()["next"]["question"]["round_type"] == "coding"

    async with get_session_factory()() as session:
        result = await session.execute(
            select(InterviewRound).where(InterviewRound.session_id == uuid.UUID(interview["id"]))
        )
        rounds_by_type = {r.round_type.value: r.status.value for r in result.scalars().all()}
        assert rounds_by_type["coding"] == "active"  # reached, not skipped
        assert rounds_by_type["introduction"] == "completed"
        assert rounds_by_type["technical"] == "completed"


# ===========================================================================
# RESUME GROUNDING
# ===========================================================================


async def test_questions_grounded_when_resume_provided(client: AsyncClient) -> None:
    token = await _register(client, email="resume1@example.com")
    resume_id = await _upload_and_analyze(client, token, role_key="backend_engineer")
    role = await _find_role(client, token, role_key="backend_engineer", company_id=None)
    template = await _find_template(client, token, role_id=role["id"], name="Technical Mock")
    interview = await _plan(
        client,
        token,
        {
            "role_id": role["id"],
            "template_id": template["id"],
            "resume_id": resume_id,
            "difficulty": "medium",
        },
    )
    started = await _start(client, token, interview["id"])
    assert started.status_code == 200, started.text
    question = started.json()["question"]
    assert question["question_text"]
    # FakeInterviewAgentProvider grounds only using skills actually present
    # on the resume — never a fabricated claim (module §16).
    assert question["question_text"].split("about ", 1)[1].split(" in", 1)[0] in (
        "Python",
        "JavaScript",
        "FastAPI",
        "PostgreSQL",
        "Docker",
        "AWS",
        "Redis",
        "Kubernetes",
    )


async def test_questions_use_generic_topic_without_resume(client: AsyncClient) -> None:
    token = await _register(client, email="resume2@example.com")
    interview = await _plan_behavioral_prep(client, token)
    started = await _start(client, token, interview["id"])
    question = started.json()["question"]
    assert "fundamentals" in question["topic"]


# ===========================================================================
# CURRENT TURN / SECURITY
# ===========================================================================


async def test_current_turn_reflects_pending_question_without_side_effects(
    client: AsyncClient,
) -> None:
    token = await _register(client, email="turn1@example.com")
    interview = await _plan_behavioral_prep(client, token)
    started = await _start(client, token, interview["id"])
    question_id = started.json()["question"]["id"]

    provider = get_fake_interview_agent_provider()
    calls_before = len(provider.calls)

    turn = await _current_turn(client, token, interview["id"])
    assert turn.status_code == 200, turn.text
    assert turn.json()["question"]["id"] == question_id
    assert turn.json()["interview_complete"] is False
    # A pure read must never call the provider.
    assert len(provider.calls) == calls_before


async def test_other_user_cannot_access_current_turn_or_answer(client: AsyncClient) -> None:
    owner_token = await _register(client, email="sec1-owner@example.com")
    interview = await _plan_behavioral_prep(client, owner_token)
    started = await _start(client, owner_token, interview["id"])
    question_id = started.json()["question"]["id"]

    attacker_token = await _register(client, email="sec1-attacker@example.com")
    turn = await _current_turn(client, attacker_token, interview["id"])
    assert turn.status_code == 404

    answer = await _answer(client, attacker_token, interview["id"], question_id, "nope")
    assert answer.status_code == 404


async def test_response_exposes_no_internal_reasoning_fields(client: AsyncClient) -> None:
    token = await _register(client, email="sec2@example.com")
    interview = await _plan_behavioral_prep(client, token)
    started = await _start(client, token, interview["id"])
    question_id = started.json()["question"]["id"]

    response = await _answer(client, token, interview["id"], question_id, "an answer")
    body = response.json()
    forbidden_keys = {"knowledge_context", "prompt", "reasoning", "chain_of_thought", "thoughts"}
    assert forbidden_keys.isdisjoint(body.keys())
    assert forbidden_keys.isdisjoint(body["evaluation"].keys())


# ===========================================================================
# LLM FAILURE HANDLING
# ===========================================================================


async def test_provider_failure_preserves_answer_and_retry_succeeds(client: AsyncClient) -> None:
    token = await _register(client, email="failure1@example.com")
    interview = await _plan_behavioral_prep(client, token)
    started = await _start(client, token, interview["id"])
    question_id = started.json()["question"]["id"]

    provider = get_fake_interview_agent_provider()
    provider.fail = True

    failed = await _answer(client, token, interview["id"], question_id, "an answer that will fail")
    assert failed.status_code == 503, failed.text
    assert failed.json()["error"]["code"] == "INTERVIEW_ENGINE_UNAVAILABLE"

    async with get_session_factory()() as session:
        result = await session.execute(
            select(Answer).where(Answer.question_id == uuid.UUID(question_id))
        )
        answers = result.scalars().all()
        assert len(answers) == 1  # preserved despite the provider failure
        assert answers[0].answer_text == "an answer that will fail"

    provider.fail = False
    retried = await _answer(client, token, interview["id"], question_id, "an answer that will fail")
    assert retried.status_code == 200, retried.text

    async with get_session_factory()() as session:
        result = await session.execute(
            select(Answer).where(Answer.question_id == uuid.UUID(question_id))
        )
        assert len(result.scalars().all()) == 1  # still exactly one — no duplicate turn


async def test_provider_timeout_returns_clean_error(client: AsyncClient) -> None:
    token = await _register(client, email="failure2@example.com")
    interview = await _plan_behavioral_prep(client, token)
    started = await _start(client, token, interview["id"])
    question_id = started.json()["question"]["id"]

    provider = get_fake_interview_agent_provider()
    provider.timeout = True

    response = await _answer(client, token, interview["id"], question_id, "will time out")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "INTERVIEW_ENGINE_TIMEOUT"


# ===========================================================================
# ABANDON
# ===========================================================================


async def test_abandon_sets_status(client: AsyncClient) -> None:
    token = await _register(client, email="abandon1@example.com")
    interview = await _plan_behavioral_prep(client, token)
    await _start(client, token, interview["id"])

    response = await _abandon(client, token, interview["id"])
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "abandoned"
    assert response.json()["completed_at"] is not None


async def test_cannot_abandon_completed_interview(client: AsyncClient) -> None:
    token = await _register(client, email="abandon2@example.com")
    interview = await _plan_behavioral_prep(client, token)
    started = await _start(client, token, interview["id"])
    question_id = started.json()["question"]["id"]

    provider = get_fake_interview_agent_provider()
    provider.forced_follow_up_worthy = False
    for _ in range(3):  # introduction(1) + behavioral(2)
        response = await _answer(client, token, interview["id"], question_id, "answer")
        if response.json()["next"]["type"] == "session_complete":
            break
        question_id = response.json()["next"]["question"]["id"]
    assert response.json()["status"] == "completed"

    abandon_response = await _abandon(client, token, interview["id"])
    assert abandon_response.status_code == 409
    assert abandon_response.json()["error"]["code"] == "INVALID_STATE_TRANSITION"
