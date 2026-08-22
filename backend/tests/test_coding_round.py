"""Module 6 (Real Coding Round & Code Evaluation Engine) tests.

Uses FakeCodeExecutor/FakeCodeEvaluationProvider (deterministic, no real
sandbox/network) — CODE_EXECUTION_BACKEND=fake, CODE_EVALUATION_PROVIDER=fake
in .env.test. Never depends on the real `executor` container or live
Gemini for this automated suite (module §24). At least one test in this
whole codebase DOES execute real candidate code through the actual
configured sandbox — see tests/test_sandbox_security.py, which is
deliberately excluded from this file's fake-provider approach.

Every test reaches a coding question via the "Coding Practice" template
(mode=coding_only, role=general_software_engineer, a single coding round
at sequence_no 1 — see app/services/planning/data/catalog.json) unless a
test specifically needs a mixed-round plan.

Under httpx's ASGITransport (the `client` fixture), FastAPI's
BackgroundTasks — and therefore the `run_code_submission` job this whole
module hinges on — execute synchronously within the same request/response
cycle, before `client.post(...)` returns (Starlette awaits
`response.background` before the ASGI call completes). So a submission
POST's response already reflects the QUEUED row, but by the time control
returns to the test, grading has already happened — no polling loop is
needed here the way a real deployment's client would need one.
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.db.session import get_session_factory
from app.execution.fake_executor import get_fake_code_executor
from app.models.enums import RoundStatus, SessionStatus
from app.models.interview import Answer, CodeSubmission, InterviewRound
from app.repositories.coding import CodeSubmissionRepository
from app.services.code_evaluation.fake_provider import get_fake_code_evaluation_provider

VALID_PASSWORD = "correct-horse-42"


# --- helpers (mirrors tests/test_interview_execution.py's conventions) -----


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


async def _plan_coding_practice(
    client: AsyncClient, token: str, *, difficulty: str = "medium"
) -> dict:
    role = await _find_role(client, token, role_key="software_engineer", company_id=None)
    template = await _find_template(client, token, role_id=role["id"], name="Coding Practice")
    response = await client.post(
        "/api/v1/interview-sessions",
        headers=_auth(token),
        json={"role_id": role["id"], "template_id": template["id"], "difficulty": difficulty},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _start(client: AsyncClient, token: str, interview_id: str):
    return await client.post(
        f"/api/v1/interview-sessions/{interview_id}/start", headers=_auth(token)
    )


async def _start_coding(client: AsyncClient, token: str) -> tuple[str, str]:
    """Registers, plans a Coding Practice interview, starts it — returns
    (interview_id, question_id) for its one coding question.
    """
    interview = await _plan_coding_practice(client, token)
    started = await _start(client, token, interview["id"])
    assert started.status_code == 200, started.text
    body = started.json()
    assert body["question"]["round_type"] == "coding"
    return interview["id"], body["question"]["id"]


async def _get_problem(client: AsyncClient, token: str, interview_id: str, question_id: str):
    return await client.get(
        f"/api/v1/interview-sessions/{interview_id}/questions/{question_id}/coding-problem",
        headers=_auth(token),
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


async def _get_submission(client: AsyncClient, token: str, interview_id: str, submission_id: str):
    return await client.get(
        f"/api/v1/interview-sessions/{interview_id}/code-submissions/{submission_id}",
        headers=_auth(token),
    )


async def _submit_and_grade(
    client: AsyncClient,
    token: str,
    interview_id: str,
    question_id: str,
    *,
    source_code: str,
    language: str = "python",
    is_final: bool = False,
) -> dict:
    """POSTs a submission, then GETs it back — the POST response body is
    always serialized BEFORE FastAPI's BackgroundTasks run the grading job
    (Starlette sends the response, then awaits `response.background` —
    module docstring), so it can only ever show the pre-grading QUEUED
    state, never the result, even though the job has genuinely finished by
    the time `client.post(...)` itself returns control to the test. A
    follow-up GET is how a real client would poll for the result too —
    this just never needs more than one round-trip under the synchronous
    ASGITransport background-task execution this suite runs under.
    """
    created = await _submit_code(
        client,
        token,
        interview_id,
        question_id,
        source_code=source_code,
        language=language,
        is_final=is_final,
    )
    assert created.status_code == 202, created.text
    graded = await _get_submission(client, token, interview_id, created.json()["id"])
    assert graded.status_code == 200, graded.text
    return graded.json()


async def _get_evaluation(client: AsyncClient, token: str, interview_id: str, submission_id: str):
    return await client.get(
        f"/api/v1/interview-sessions/{interview_id}/code-submissions/{submission_id}/evaluation",
        headers=_auth(token),
    )


# ===========================================================================
# CODING PROBLEM RETRIEVAL — hidden tests never leave the service boundary
# ===========================================================================


async def test_coding_problem_exposes_only_sample_test_cases(client: AsyncClient) -> None:
    token = await _register(client, email="problem1@example.com")
    interview_id, question_id = await _start_coding(client, token)

    response = await _get_problem(client, token, interview_id, question_id)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["difficulty"] == "medium"
    assert body["sample_test_cases"], "every catalog problem has at least one sample test case"
    for tc in body["sample_test_cases"]:
        assert "input" in tc and "expected_output" in tc
    assert "python" in body["starter_code"]
    assert "python" in body["supported_languages"]


async def test_non_coding_question_rejected_by_coding_endpoints(client: AsyncClient) -> None:
    token = await _register(client, email="problem2@example.com")
    # Behavioral Prep's first question is introduction — not a coding type.
    role = await _find_role(client, token, role_key="software_engineer", company_id=None)
    template = await _find_template(client, token, role_id=role["id"], name="Behavioral Prep")
    plan = await client.post(
        "/api/v1/interview-sessions",
        headers=_auth(token),
        json={"role_id": role["id"], "template_id": template["id"], "difficulty": "medium"},
    )
    interview_id = plan.json()["id"]
    started = await _start(client, token, interview_id)
    non_coding_question_id = started.json()["question"]["id"]

    response = await _get_problem(client, token, interview_id, non_coding_question_id)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CODING_QUESTION_NOT_FOUND"


# ===========================================================================
# RUN vs SUBMIT — module §6's mandatory distinction
# ===========================================================================


async def test_run_only_executes_sample_tests_and_never_evaluates(client: AsyncClient) -> None:
    token = await _register(client, email="run1@example.com")
    interview_id, question_id = await _start_coding(client, token)
    problem = (await _get_problem(client, token, interview_id, question_id)).json()
    sample_count = len(problem["sample_test_cases"])

    submission = await _submit_and_grade(
        client, token, interview_id, question_id, source_code="# CORRECT_SOLUTION", is_final=False
    )
    assert submission["is_final"] is False
    assert submission["attempt_no"] == 1
    assert submission["execution_status"] == "success"
    assert submission["total_test_count"] == sample_count  # never the hidden ones too

    evaluation = await _get_evaluation(client, token, interview_id, submission["id"])
    assert evaluation.status_code == 200
    assert evaluation.json() is None  # Run never triggers CodeEvaluationProvider
    assert get_fake_code_evaluation_provider().calls == []


async def test_submit_executes_all_tests_and_triggers_evaluation(client: AsyncClient) -> None:
    token = await _register(client, email="submit1@example.com")
    interview_id, question_id = await _start_coding(client, token)
    problem = (await _get_problem(client, token, interview_id, question_id)).json()
    sample_count = len(problem["sample_test_cases"])

    submission = await _submit_and_grade(
        client, token, interview_id, question_id, source_code="# CORRECT_SOLUTION", is_final=True
    )
    assert submission["is_final"] is True
    assert submission["execution_status"] == "success"
    assert submission["total_test_count"] > sample_count  # hidden tests ran too
    assert submission["passed_test_count"] == submission["total_test_count"]
    assert submission["graded_at"] is not None

    evaluation = await _get_evaluation(client, token, interview_id, submission["id"])
    assert evaluation.status_code == 200
    eval_body = evaluation.json()
    assert eval_body["correctness_score"] == 100.0
    assert eval_body["overall_code_score"] > 0
    assert get_fake_code_evaluation_provider().calls == ["evaluate"]


async def test_submit_sample_results_never_leak_hidden_test_data(client: AsyncClient) -> None:
    token = await _register(client, email="submit2@example.com")
    interview_id, question_id = await _start_coding(client, token)
    problem = (await _get_problem(client, token, interview_id, question_id)).json()
    sample_count = len(problem["sample_test_cases"])

    submission = await _submit_and_grade(
        client, token, interview_id, question_id, source_code="# CORRECT_SOLUTION", is_final=True
    )
    # sample_test_results itemizes only the sample subset even though every
    # test case (sample + hidden) ran and contributed to total_test_count.
    assert len(submission["sample_test_results"]) == sample_count
    assert submission["total_test_count"] > sample_count


# ===========================================================================
# MULTI-ATTEMPT
# ===========================================================================


async def test_multiple_runs_preserve_every_attempt(client: AsyncClient) -> None:
    token = await _register(client, email="attempt1@example.com")
    interview_id, question_id = await _start_coding(client, token)

    first = await _submit_code(
        client, token, interview_id, question_id, source_code="# INCORRECT_SOLUTION"
    )
    second = await _submit_code(
        client, token, interview_id, question_id, source_code="# CORRECT_SOLUTION"
    )
    assert first.json()["attempt_no"] == 1
    assert second.json()["attempt_no"] == 2
    assert first.json()["id"] != second.json()["id"]

    listing = await client.get(
        f"/api/v1/interview-sessions/{interview_id}/questions/{question_id}/code-submissions",
        headers=_auth(token),
    )
    assert listing.status_code == 200
    attempt_numbers = sorted(s["attempt_no"] for s in listing.json())
    assert attempt_numbers == [1, 2]


# ===========================================================================
# FINAL-SUBMISSION-ONCE (module §6/§22)
# ===========================================================================


async def test_second_final_submission_is_idempotent_replay(client: AsyncClient) -> None:
    token = await _register(client, email="final1@example.com")
    interview_id, question_id = await _start_coding(client, token)

    first = await _submit_code(
        client, token, interview_id, question_id, source_code="# CORRECT_SOLUTION", is_final=True
    )
    second = await _submit_code(
        client, token, interview_id, question_id, source_code="# INCORRECT_SOLUTION", is_final=True
    )
    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json()["id"] == second.json()["id"]  # the second call never created a new row

    async with get_session_factory()() as session:
        answer_result = await session.execute(
            select(Answer).where(Answer.question_id == uuid.UUID(question_id))
        )
        answer = answer_result.scalar_one()
        finals = await session.execute(
            select(CodeSubmission).where(
                CodeSubmission.answer_id == answer.id, CodeSubmission.is_final.is_(True)
            )
        )
        assert len(finals.scalars().all()) == 1


async def test_concurrent_final_submissions_hit_the_db_constraint_backstop(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Isolates the DB's own `ux_code_submissions_final` partial unique
    index as the thing that actually prevents two final submissions for
    the same question — not merely the Python-level pre-check in
    CodingRoundService.create_submission. Forces that pre-check to always
    report "no final exists yet" (simulating two requests both passing it
    before either commits), so the second insert can only be stopped by
    the real constraint, caught as an IntegrityError and translated to a
    clean 409 — never a silent duplicate final row.
    """
    token = await _register(client, email="final2@example.com")
    interview_id, question_id = await _start_coding(client, token)

    first = await _submit_code(
        client, token, interview_id, question_id, source_code="# CORRECT_SOLUTION", is_final=True
    )
    assert first.status_code == 202

    async def _always_lie(
        self, answer_id
    ):  # noqa: ANN001 — test monkeypatch, matches original's shape
        return None  # simulate the race: "no final exists yet", every time asked

    monkeypatch.setattr(CodeSubmissionRepository, "get_final_for_answer", _always_lie)

    second = await _submit_code(
        client, token, interview_id, question_id, source_code="# INCORRECT_SOLUTION", is_final=True
    )
    assert second.status_code == 409, second.text
    assert second.json()["error"]["code"] == "CODE_SUBMISSION_RACE"

    # The DB constraint held: exactly one final row exists, regardless of
    # the lying pre-check.
    async with get_session_factory()() as session:
        answer_result = await session.execute(
            select(Answer).where(Answer.question_id == uuid.UUID(question_id))
        )
        answer = answer_result.scalar_one()
        finals = await session.execute(
            select(CodeSubmission).where(
                CodeSubmission.answer_id == answer.id, CodeSubmission.is_final.is_(True)
            )
        )
        assert len(finals.scalars().all()) == 1


# ===========================================================================
# FAILURE HANDLING (module §9/§22)
# ===========================================================================


async def test_compile_error_is_a_final_graded_verdict_with_no_llm_call(
    client: AsyncClient,
) -> None:
    token = await _register(client, email="fail1@example.com")
    interview_id, question_id = await _start_coding(client, token)

    submission = await _submit_and_grade(
        client, token, interview_id, question_id, source_code="# COMPILE_ERROR", is_final=True
    )
    assert submission["execution_status"] == "compile_error"
    assert submission["is_final"] is True  # a real verdict — no retry needed or allowed
    assert submission["error_message"]

    evaluation = await _get_evaluation(client, token, interview_id, submission["id"])
    eval_body = evaluation.json()
    assert eval_body["correctness_score"] == 0.0
    assert eval_body["overall_code_score"] == 0.0
    # No LLM call was spent judging quality of code that never compiled.
    assert get_fake_code_evaluation_provider().calls == []

    # A compile error is final and graded — a second Submit replays it,
    # never creates a fresh attempt.
    retry = await _submit_code(
        client, token, interview_id, question_id, source_code="# CORRECT_SOLUTION", is_final=True
    )
    assert retry.json()["id"] == submission["id"]


async def test_executor_infra_failure_releases_final_slot_for_retry(client: AsyncClient) -> None:
    token = await _register(client, email="fail2@example.com")
    interview_id, question_id = await _start_coding(client, token)

    get_fake_code_executor().fail = True
    try:
        failed = await _submit_and_grade(
            client,
            token,
            interview_id,
            question_id,
            source_code="# CORRECT_SOLUTION",
            is_final=True,
        )
    finally:
        get_fake_code_executor().fail = False

    assert failed["execution_status"] == "error"
    assert failed["is_final"] is False  # released — never the candidate's fault
    assert failed["error_message"]

    # A genuine retry (executor healthy again) succeeds as a fresh final.
    retried = await _submit_and_grade(
        client, token, interview_id, question_id, source_code="# CORRECT_SOLUTION", is_final=True
    )
    assert retried["id"] != failed["id"]
    assert retried["is_final"] is True
    assert retried["execution_status"] == "success"


async def test_evaluation_provider_failure_releases_final_slot_for_retry(
    client: AsyncClient,
) -> None:
    token = await _register(client, email="fail3@example.com")
    interview_id, question_id = await _start_coding(client, token)

    get_fake_code_evaluation_provider().fail = True
    try:
        failed = await _submit_and_grade(
            client,
            token,
            interview_id,
            question_id,
            source_code="# CORRECT_SOLUTION",
            is_final=True,
        )
    finally:
        get_fake_code_evaluation_provider().fail = False

    # Execution itself succeeded — only grading (the LLM step) failed.
    assert failed["execution_status"] == "success"
    assert failed["is_final"] is False
    assert failed["error_message"]
    assert (await _get_evaluation(client, token, interview_id, failed["id"])).json() is None

    retried = await _submit_and_grade(
        client, token, interview_id, question_id, source_code="# CORRECT_SOLUTION", is_final=True
    )
    assert retried["id"] != failed["id"]
    assert retried["is_final"] is True
    evaluation = await _get_evaluation(client, token, interview_id, retried["id"])
    assert evaluation.json() is not None


async def test_timeout_and_runtime_error_are_distinct_final_statuses(client: AsyncClient) -> None:
    token = await _register(client, email="fail4@example.com")
    interview_id, question_id = await _start_coding(client, token)

    timeout_submission = await _submit_and_grade(
        client, token, interview_id, question_id, source_code="# TIME_LIMIT", is_final=True
    )
    assert timeout_submission["execution_status"] == "timeout"

    token2 = await _register(client, email="fail5@example.com")
    interview_id2, question_id2 = await _start_coding(client, token2)
    runtime_submission = await _submit_and_grade(
        client, token2, interview_id2, question_id2, source_code="# RUNTIME_ERROR", is_final=True
    )
    assert runtime_submission["execution_status"] == "runtime_error"


# ===========================================================================
# OWNERSHIP
# ===========================================================================


async def test_other_candidate_cannot_touch_someone_elses_coding_question(
    client: AsyncClient,
) -> None:
    owner_token = await _register(client, email="owner1@example.com")
    interview_id, question_id = await _start_coding(client, owner_token)

    attacker_token = await _register(client, email="attacker1@example.com")
    problem = await _get_problem(client, attacker_token, interview_id, question_id)
    assert problem.status_code == 404

    submit = await _submit_code(
        client, attacker_token, interview_id, question_id, source_code="# CORRECT_SOLUTION"
    )
    assert submit.status_code == 404

    owner_submission = await _submit_code(
        client, owner_token, interview_id, question_id, source_code="# CORRECT_SOLUTION"
    )
    get = await _get_submission(client, attacker_token, interview_id, owner_submission.json()["id"])
    assert get.status_code == 404


# ===========================================================================
# UNSUPPORTED LANGUAGE
# ===========================================================================


async def test_unsupported_language_is_rejected(client: AsyncClient) -> None:
    token = await _register(client, email="lang1@example.com")
    interview_id, question_id = await _start_coding(client, token)

    response = await _submit_code(
        client,
        token,
        interview_id,
        question_id,
        source_code="puts 'hi'",
        language="ruby",
        is_final=False,
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "UNSUPPORTED_LANGUAGE"


# ===========================================================================
# GRAPH INTEGRATION — a final submission completes the round and interview
# ===========================================================================


async def test_final_submission_completes_round_and_interview(client: AsyncClient) -> None:
    """Coding Practice has exactly one round, so a graded final submission
    must complete both the round AND the whole interview via the
    CODING_ROUND_COMPLETE graph trigger (module §9).
    """
    token = await _register(client, email="complete1@example.com")
    interview_id, question_id = await _start_coding(client, token)

    response = await _submit_code(
        client, token, interview_id, question_id, source_code="# CORRECT_SOLUTION", is_final=True
    )
    assert response.status_code == 202

    detail = await client.get(f"/api/v1/interview-sessions/{interview_id}", headers=_auth(token))
    assert detail.json()["status"] == "completed"

    async with get_session_factory()() as session:
        result = await session.execute(
            select(InterviewRound).where(InterviewRound.session_id == uuid.UUID(interview_id))
        )
        rounds = result.scalars().all()
        assert all(r.status == RoundStatus.COMPLETED for r in rounds)


async def test_run_never_advances_the_round(client: AsyncClient) -> None:
    token = await _register(client, email="norun1@example.com")
    interview_id, question_id = await _start_coding(client, token)

    response = await _submit_code(
        client, token, interview_id, question_id, source_code="# CORRECT_SOLUTION", is_final=False
    )
    assert response.status_code == 202

    detail = await client.get(f"/api/v1/interview-sessions/{interview_id}", headers=_auth(token))
    assert detail.json()["status"] == SessionStatus.IN_PROGRESS.value
