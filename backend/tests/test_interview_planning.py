"""Module 4 (Interview Planner & Interview Session Setup) tests.

Catalog data is seeded idempotently by the autouse `_seed_catalog` fixture
in conftest.py — every test can rely on the MVP catalog
(app/services/planning/data/catalog.json) already being present.
"""

import uuid

from httpx import AsyncClient

from app.db.session import get_session_factory
from app.models.planning import Company, InterviewTemplate
from app.models.resume import Resume as ResumeModel
from tests.pdf_fixtures import fictional_resume_pdf

VALID_PASSWORD = "correct-horse-42"


# --- helpers ---------------------------------------------------------------


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


async def _companies(client: AsyncClient, token: str) -> list[dict]:
    response = await client.get("/api/v1/companies", headers=_auth(token))
    assert response.status_code == 200, response.text
    return response.json()


async def _roles(client: AsyncClient, token: str) -> list[dict]:
    response = await client.get("/api/v1/roles", headers=_auth(token))
    assert response.status_code == 200, response.text
    return response.json()


async def _templates_for_role(
    client: AsyncClient, token: str, role_id: str, **params
) -> list[dict]:
    # httpx serializes params={"x": None} as the literal query string "x=",
    # not an omitted param — FastAPI then tries to parse "" as the
    # declared uuid.UUID/InterviewMode type and 422s. Drop None values so
    # callers can pass e.g. company_id=None to mean "omit this filter".
    query = {k: v for k, v in params.items() if v is not None}
    response = await client.get(
        f"/api/v1/roles/{role_id}/templates", headers=_auth(token), params=query
    )
    assert response.status_code == 200, response.text
    return response.json()


async def _find_role(client: AsyncClient, token: str, *, role_key: str, company_id=None) -> dict:
    roles = await _roles(client, token)
    for r in roles:
        if r["role_key"] == role_key and r["company_id"] == company_id:
            return r
    raise AssertionError(f"role_key={role_key} company_id={company_id} not found in {roles}")


async def _find_company(client: AsyncClient, token: str, *, slug: str) -> dict:
    companies = await _companies(client, token)
    for c in companies:
        if c["slug"] == slug:
            return c
    raise AssertionError(f"company slug={slug} not found in {companies}")


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
    """Uploads the fictional resume fixture, waits for (synchronous, under
    ASGITransport) processing to complete, and runs gap-analysis against
    role_key so resume_gap_analysis exists for AUTO-difficulty tests.
    Returns the resume id.
    """
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


async def _plan(client: AsyncClient, token: str, body: dict):
    return await client.post("/api/v1/interview-sessions", headers=_auth(token), json=body)


# ===========================================================================
# CATALOG
# ===========================================================================


async def test_list_companies_returns_seeded_mvp_catalog(client: AsyncClient) -> None:
    token = await _register(client, email="catalog1@example.com")
    companies = await _companies(client, token)
    slugs = {c["slug"] for c in companies}
    assert {"general", "google", "microsoft", "amazon", "atlassian", "openai"} <= slugs


async def test_list_roles_returns_seeded_roles(client: AsyncClient) -> None:
    token = await _register(client, email="catalog2@example.com")
    roles = await _roles(client, token)
    role_keys = {r["role_key"] for r in roles}
    assert {
        "software_engineer",
        "backend_engineer",
        "ai_engineer",
        "ml_engineer",
        "data_engineer",
    } <= role_keys


async def test_list_roles_filters_by_level(client: AsyncClient) -> None:
    token = await _register(client, email="catalog3@example.com")
    response = await client.get("/api/v1/roles", headers=_auth(token), params={"level": "mid"})
    assert response.status_code == 200
    assert all(r["level"] == "mid" for r in response.json())

    response = await client.get("/api/v1/roles", headers=_auth(token), params={"level": "staff"})
    assert response.status_code == 200
    assert response.json() == []


async def test_company_roles_endpoint_scopes_to_company(client: AsyncClient) -> None:
    token = await _register(client, email="catalog4@example.com")
    google = await _find_company(client, token, slug="google")
    response = await client.get(f"/api/v1/companies/{google['id']}/roles", headers=_auth(token))
    assert response.status_code == 200
    roles = response.json()
    assert roles
    assert all(r["company_id"] == google["id"] for r in roles)


async def test_template_filtering_by_company_and_mode(client: AsyncClient) -> None:
    token = await _register(client, email="catalog5@example.com")
    role = await _find_role(client, token, role_key="software_engineer", company_id=None)
    all_templates = await _templates_for_role(client, token, role["id"])
    assert len(all_templates) >= 4  # full_mock, coding_only, behavioral_only, resume_deep_dive

    technical_only = await _templates_for_role(client, token, role["id"], mode="coding_only")
    assert len(technical_only) == 1
    assert technical_only[0]["mode"] == "coding_only"


async def test_get_template_detail_includes_ordered_rounds(client: AsyncClient) -> None:
    token = await _register(client, email="catalog6@example.com")
    role = await _find_role(client, token, role_key="software_engineer", company_id=None)
    template = await _find_template(client, token, role_id=role["id"], name="Full Mock Interview")
    response = await client.get(f"/api/v1/templates/{template['id']}", headers=_auth(token))
    assert response.status_code == 200
    body = response.json()
    sequence_numbers = [r["sequence_no"] for r in body["rounds"]]
    assert sequence_numbers == sorted(sequence_numbers)
    assert abs(sum(float(r["weight"]) for r in body["rounds"]) - 1.0) < 1e-6


async def test_inactive_company_excluded_from_listing_and_rejected(client: AsyncClient) -> None:
    token = await _register(client, email="catalog7@example.com")
    general = await _find_company(client, token, slug="general")

    async with get_session_factory()() as session:
        company = await session.get(Company, uuid.UUID(general["id"]))
        company.is_active = False
        await session.commit()

    try:
        companies = await _companies(client, token)
        assert general["id"] not in {c["id"] for c in companies}

        response = await client.get(
            f"/api/v1/companies/{general['id']}/roles", headers=_auth(token)
        )
        assert response.status_code == 404
    finally:
        async with get_session_factory()() as session:
            company = await session.get(Company, uuid.UUID(general["id"]))
            company.is_active = True
            await session.commit()


# ===========================================================================
# PLANNING
# ===========================================================================


async def test_create_generic_interview_plan_no_resume(client: AsyncClient) -> None:
    token = await _register(client, email="plan1@example.com")
    role = await _find_role(client, token, role_key="software_engineer", company_id=None)
    template = await _find_template(client, token, role_id=role["id"], name="Coding Practice")

    response = await _plan(
        client,
        token,
        {"role_id": role["id"], "template_id": template["id"], "difficulty": "medium"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "not_started"
    assert body["resume_id"] is None
    assert body["mode"] == "coding_only"
    assert body["requested_difficulty"] == "medium"
    assert body["starting_difficulty"] == "medium"
    assert body["current_difficulty"] == "medium"


async def test_plan_endpoint_returns_null_company_for_company_agnostic_interview(
    client: AsyncClient,
) -> None:
    """Regression: InterviewPlanResponse.company must accept None — a
    company-agnostic plan's snapshot legitimately has company=None
    (InterviewSession.company_id is nullable), and GET .../plan used to
    500 with a pydantic ValidationError on this exact case.
    """
    token = await _register(client, email="plan-null-company@example.com")
    role = await _find_role(client, token, role_key="software_engineer", company_id=None)
    template = await _find_template(client, token, role_id=role["id"], name="Coding Practice")

    created = await _plan(
        client,
        token,
        {"role_id": role["id"], "template_id": template["id"], "difficulty": "medium"},
    )
    assert created.status_code == 201, created.text

    plan = await client.get(
        f"/api/v1/interview-sessions/{created.json()['id']}/plan", headers=_auth(token)
    )
    assert plan.status_code == 200, plan.text
    assert plan.json()["company"] is None


async def test_create_resume_aware_interview_plan(client: AsyncClient) -> None:
    token = await _register(client, email="plan2@example.com")
    resume_id = await _upload_and_analyze(client, token, role_key="backend_engineer")
    role = await _find_role(client, token, role_key="backend_engineer", company_id=None)
    template = await _find_template(client, token, role_id=role["id"], name="Technical Mock")

    response = await _plan(
        client,
        token,
        {
            "role_id": role["id"],
            "template_id": template["id"],
            "resume_id": resume_id,
            "difficulty": "medium",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["resume_id"] == resume_id

    plan = await client.get(f"/api/v1/interview-sessions/{body['id']}/plan", headers=_auth(token))
    assert plan.status_code == 200, plan.text
    plan_body = plan.json()
    assert plan_body["personalization"] is not None
    assert (
        "PostgreSQL" in plan_body["personalization"]["skills"]
        or "Python" in plan_body["personalization"]["skills"]
    )


async def test_manual_difficulty_is_used_verbatim(client: AsyncClient) -> None:
    token = await _register(client, email="plan3@example.com")
    role = await _find_role(client, token, role_key="software_engineer", company_id=None)
    template = await _find_template(client, token, role_id=role["id"], name="Coding Practice")

    response = await _plan(
        client,
        token,
        {"role_id": role["id"], "template_id": template["id"], "difficulty": "hard"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["requested_difficulty"] == "hard"
    assert body["starting_difficulty"] == "hard"


async def test_auto_difficulty_uses_resume_gap_analysis(client: AsyncClient) -> None:
    token = await _register(client, email="plan4@example.com")
    resume_id = await _upload_and_analyze(client, token, role_key="backend_engineer")
    role = await _find_role(client, token, role_key="backend_engineer", company_id=None)
    template = await _find_template(client, token, role_id=role["id"], name="Technical Mock")

    response = await _plan(
        client,
        token,
        {
            "role_id": role["id"],
            "template_id": template["id"],
            "resume_id": resume_id,
            "difficulty": "auto",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["requested_difficulty"] == "auto"
    assert body["starting_difficulty"] in {"easy", "medium", "hard"}

    plan = await client.get(f"/api/v1/interview-sessions/{body['id']}/plan", headers=_auth(token))
    reasons = plan.json()["difficulty"]["reasons"]
    assert any("gap-analysis" in r.lower() or "auto" in r.lower() for r in reasons)


async def test_auto_difficulty_without_resume_uses_safe_default(client: AsyncClient) -> None:
    token = await _register(client, email="plan5@example.com")
    role = await _find_role(client, token, role_key="software_engineer", company_id=None)
    template = await _find_template(client, token, role_id=role["id"], name="Coding Practice")

    response = await _plan(
        client,
        token,
        {"role_id": role["id"], "template_id": template["id"], "difficulty": "auto"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["starting_difficulty"] == "medium"  # documented safe default

    plan = await client.get(f"/api/v1/interview-sessions/{body['id']}/plan", headers=_auth(token))
    reasons = plan.json()["difficulty"]["reasons"]
    assert any("safe default" in r.lower() for r in reasons)


async def test_rounds_generated_from_template_preserve_order_and_weights(
    client: AsyncClient,
) -> None:
    token = await _register(client, email="plan6@example.com")
    # "Full Mock Interview" includes a resume_discussion round, so planning
    # against it requires an analyzed resume (module §8) — without one the
    # service correctly 422s with RESUME_REQUIRED before any rounds are
    # ever generated, which isn't what this test is checking.
    resume_id = await _upload_and_analyze(client, token, role_key="software_engineer")
    role = await _find_role(client, token, role_key="software_engineer", company_id=None)
    template = await _find_template(client, token, role_id=role["id"], name="Full Mock Interview")
    template_detail = await client.get(f"/api/v1/templates/{template['id']}", headers=_auth(token))
    template_rounds = template_detail.json()["rounds"]

    response = await _plan(
        client,
        token,
        {
            "role_id": role["id"],
            "template_id": template["id"],
            "resume_id": resume_id,
            "difficulty": "medium",
        },
    )
    assert response.status_code == 201, response.text
    interview_id = response.json()["id"]

    plan = await client.get(f"/api/v1/interview-sessions/{interview_id}/plan", headers=_auth(token))
    plan_rounds = plan.json()["rounds"]
    assert [r["round_type"] for r in plan_rounds] == [r["round_type"] for r in template_rounds]
    assert [r["sequence_no"] for r in plan_rounds] == [r["sequence_no"] for r in template_rounds]
    for pr, tr in zip(plan_rounds, template_rounds, strict=False):
        assert abs(float(pr["weight"]) - float(tr["weight"])) < 1e-6


# ===========================================================================
# RESUME
# ===========================================================================


async def test_omitted_resume_id_uses_active_resume(client: AsyncClient) -> None:
    token = await _register(client, email="resume1@example.com")
    resume_id = await _upload_and_analyze(client, token, role_key="software_engineer")
    role = await _find_role(client, token, role_key="software_engineer", company_id=None)
    template = await _find_template(client, token, role_id=role["id"], name="Coding Practice")

    response = await _plan(client, token, {"role_id": role["id"], "template_id": template["id"]})
    assert response.status_code == 201, response.text
    assert response.json()["resume_id"] == resume_id


async def test_explicit_resume_id_pins_exact_version(client: AsyncClient) -> None:
    token = await _register(client, email="resume2@example.com")
    first_resume_id = await _upload_and_analyze(client, token, role_key="software_engineer")
    # Upload a second resume — becomes the new active one; first is retained
    # but no longer active (module §8 versioning, reused from Module 3).
    second_resume_id = await _upload_and_analyze(client, token, role_key="software_engineer")
    assert second_resume_id != first_resume_id

    role = await _find_role(client, token, role_key="software_engineer", company_id=None)
    template = await _find_template(client, token, role_id=role["id"], name="Coding Practice")

    response = await _plan(
        client,
        token,
        {"role_id": role["id"], "template_id": template["id"], "resume_id": first_resume_id},
    )
    assert response.status_code == 201, response.text
    assert response.json()["resume_id"] == first_resume_id


async def test_cross_user_resume_rejected(client: AsyncClient) -> None:
    owner_token = await _register(client, email="resume-owner@example.com")
    resume_id = await _upload_and_analyze(client, owner_token, role_key="software_engineer")

    attacker_token = await _register(client, email="resume-attacker@example.com")
    role = await _find_role(client, attacker_token, role_key="software_engineer", company_id=None)
    template = await _find_template(
        client, attacker_token, role_id=role["id"], name="Coding Practice"
    )

    response = await _plan(
        client,
        attacker_token,
        {"role_id": role["id"], "template_id": template["id"], "resume_id": resume_id},
    )
    assert response.status_code == 404


async def test_pending_resume_rejected_when_explicitly_selected(client: AsyncClient) -> None:
    token = await _register(client, email="resume3@example.com")
    upload = await client.post(
        "/api/v1/resumes",
        headers=_auth(token),
        files={"file": ("resume.pdf", fictional_resume_pdf(), "application/pdf")},
    )
    assert upload.status_code == 201
    resume_id = upload.json()["id"]

    # Force the row back to "pending" to simulate a not-yet-processed
    # resume regardless of how fast the fake pipeline actually settles it.
    async with get_session_factory()() as session:
        resume = await session.get(ResumeModel, uuid.UUID(resume_id))
        resume.parsed_status = "pending"
        await session.commit()

    role = await _find_role(client, token, role_key="software_engineer", company_id=None)
    template = await _find_template(client, token, role_id=role["id"], name="Coding Practice")

    response = await _plan(
        client,
        token,
        {"role_id": role["id"], "template_id": template["id"], "resume_id": resume_id},
    )
    assert response.status_code == 409


async def test_resume_deep_dive_requires_analyzed_resume(client: AsyncClient) -> None:
    token = await _register(client, email="resume4@example.com")
    role = await _find_role(client, token, role_key="software_engineer", company_id=None)
    template = await _find_template(client, token, role_id=role["id"], name="Resume Deep Dive")

    response = await _plan(client, token, {"role_id": role["id"], "template_id": template["id"]})
    assert response.status_code == 422


# ===========================================================================
# OWNERSHIP
# ===========================================================================


async def test_own_interview_retrievable(client: AsyncClient) -> None:
    token = await _register(client, email="own1@example.com")
    role = await _find_role(client, token, role_key="software_engineer", company_id=None)
    template = await _find_template(client, token, role_id=role["id"], name="Coding Practice")
    created = await _plan(client, token, {"role_id": role["id"], "template_id": template["id"]})
    interview_id = created.json()["id"]

    detail = await client.get(f"/api/v1/interview-sessions/{interview_id}", headers=_auth(token))
    assert detail.status_code == 200
    listing = await client.get("/api/v1/interview-sessions", headers=_auth(token))
    assert interview_id in {i["id"] for i in listing.json()}


async def test_other_users_interview_returns_404(client: AsyncClient) -> None:
    owner_token = await _register(client, email="own2-owner@example.com")
    role = await _find_role(client, owner_token, role_key="software_engineer", company_id=None)
    template = await _find_template(client, owner_token, role_id=role["id"], name="Coding Practice")
    created = await _plan(
        client, owner_token, {"role_id": role["id"], "template_id": template["id"]}
    )
    interview_id = created.json()["id"]

    other_token = await _register(client, email="own2-other@example.com")
    detail = await client.get(
        f"/api/v1/interview-sessions/{interview_id}", headers=_auth(other_token)
    )
    assert detail.status_code == 404

    plan = await client.get(
        f"/api/v1/interview-sessions/{interview_id}/plan", headers=_auth(other_token)
    )
    assert plan.status_code == 404


# ===========================================================================
# VALIDATION
# ===========================================================================


async def test_invalid_company_id_rejected(client: AsyncClient) -> None:
    token = await _register(client, email="val1@example.com")
    role = await _find_role(client, token, role_key="software_engineer", company_id=None)
    template = await _find_template(client, token, role_id=role["id"], name="Coding Practice")

    response = await _plan(
        client,
        token,
        {
            "company_id": str(uuid.uuid4()),
            "role_id": role["id"],
            "template_id": template["id"],
        },
    )
    assert response.status_code == 404


async def test_invalid_role_id_rejected(client: AsyncClient) -> None:
    token = await _register(client, email="val2@example.com")
    role = await _find_role(client, token, role_key="software_engineer", company_id=None)
    template = await _find_template(client, token, role_id=role["id"], name="Coding Practice")

    response = await _plan(
        client, token, {"role_id": str(uuid.uuid4()), "template_id": template["id"]}
    )
    assert response.status_code == 404


async def test_template_role_mismatch_rejected(client: AsyncClient) -> None:
    token = await _register(client, email="val3@example.com")
    swe_role = await _find_role(client, token, role_key="software_engineer", company_id=None)
    backend_role = await _find_role(client, token, role_key="backend_engineer", company_id=None)
    template = await _find_template(
        client, token, role_id=backend_role["id"], name="Technical Mock"
    )

    response = await _plan(
        client, token, {"role_id": swe_role["id"], "template_id": template["id"]}
    )
    assert response.status_code == 422


async def test_template_company_mismatch_rejected(client: AsyncClient) -> None:
    token = await _register(client, email="val4@example.com")
    google = await _find_company(client, token, slug="google")
    google_role = await _find_role(
        client, token, role_key="software_engineer", company_id=google["id"]
    )
    google_template = await _find_template(
        client,
        token,
        role_id=google_role["id"],
        name="Google SWE — Full Mock",
        company_id=google["id"],
    )

    # Omit company_id entirely — the Google-specific template requires it.
    response = await _plan(
        client, token, {"role_id": google_role["id"], "template_id": google_template["id"]}
    )
    assert response.status_code == 422


async def test_incompatible_mode_rejected(client: AsyncClient) -> None:
    token = await _register(client, email="val5@example.com")
    role = await _find_role(client, token, role_key="software_engineer", company_id=None)
    template = await _find_template(client, token, role_id=role["id"], name="Coding Practice")

    response = await _plan(
        client,
        token,
        {"role_id": role["id"], "template_id": template["id"], "mode": "behavioral_only"},
    )
    assert response.status_code == 422


async def test_inactive_template_rejected(client: AsyncClient) -> None:
    token = await _register(client, email="val6@example.com")
    role = await _find_role(client, token, role_key="software_engineer", company_id=None)
    template = await _find_template(client, token, role_id=role["id"], name="Coding Practice")

    async with get_session_factory()() as session:
        row = await session.get(InterviewTemplate, uuid.UUID(template["id"]))
        row.is_active = False
        await session.commit()

    try:
        response = await _plan(
            client, token, {"role_id": role["id"], "template_id": template["id"]}
        )
        assert response.status_code == 404
    finally:
        async with get_session_factory()() as session:
            row = await session.get(InterviewTemplate, uuid.UUID(template["id"]))
            row.is_active = True
            await session.commit()


# ===========================================================================
# SNAPSHOT IMMUTABILITY
# ===========================================================================


async def test_editing_template_after_planning_does_not_change_existing_plan(
    client: AsyncClient,
) -> None:
    token = await _register(client, email="snap1@example.com")
    role = await _find_role(client, token, role_key="software_engineer", company_id=None)
    template = await _find_template(client, token, role_id=role["id"], name="Coding Practice")

    created = await _plan(
        client, token, {"role_id": role["id"], "template_id": template["id"], "difficulty": "hard"}
    )
    interview_id = created.json()["id"]
    plan_before = await client.get(
        f"/api/v1/interview-sessions/{interview_id}/plan", headers=_auth(token)
    )
    rounds_before = plan_before.json()["rounds"]

    # Mutating this catalog row is only safe because it's reverted in the
    # finally block below — catalog tables are shared, seed-idempotent, and
    # never truncated between tests (see conftest.py's _seed_catalog), so an
    # un-reverted rename here would silently pollute every later test *and*
    # every later test run (the reseed upsert matches by (company_id,
    # role_id, name); a renamed row no longer matches "Coding Practice" and
    # a second, freshly-seeded row appears alongside it instead of replacing
    # it — this was caught live: test_template_filtering_by_company_and_mode
    # started failing on a stale DB with a duplicate "Coding Practice").
    try:
        async with get_session_factory()() as session:
            row = await session.get(InterviewTemplate, uuid.UUID(template["id"]))
            row.default_difficulty = "easy"
            row.name = "Renamed Template"
            await session.commit()

        plan_after = await client.get(
            f"/api/v1/interview-sessions/{interview_id}/plan", headers=_auth(token)
        )
        body_after = plan_after.json()
        assert body_after["rounds"] == rounds_before
        assert body_after["difficulty"]["starting"] == "hard"
        assert body_after["template"]["name"] == "Coding Practice"  # not "Renamed Template"
    finally:
        async with get_session_factory()() as session:
            row = await session.get(InterviewTemplate, uuid.UUID(template["id"]))
            row.default_difficulty = "medium"
            row.name = "Coding Practice"
            await session.commit()


async def test_newer_resume_does_not_mutate_existing_plan(client: AsyncClient) -> None:
    token = await _register(client, email="snap2@example.com")
    first_resume_id = await _upload_and_analyze(client, token, role_key="software_engineer")
    role = await _find_role(client, token, role_key="software_engineer", company_id=None)
    template = await _find_template(client, token, role_id=role["id"], name="Coding Practice")

    created = await _plan(
        client,
        token,
        {"role_id": role["id"], "template_id": template["id"], "resume_id": first_resume_id},
    )
    interview_id = created.json()["id"]

    # Upload (and analyze) a second resume — becomes the new active resume.
    await _upload_and_analyze(client, token, role_key="software_engineer")

    detail = await client.get(f"/api/v1/interview-sessions/{interview_id}", headers=_auth(token))
    assert detail.json()["resume_id"] == first_resume_id  # unchanged


# ===========================================================================
# REGRESSION (Module 2 / Module 3 spot checks — full suites live in their
# own test files; this just confirms nothing here broke authentication or
# resume ownership)
# ===========================================================================


async def test_regression_auth_still_enforced_on_planning_routes(client: AsyncClient) -> None:
    response = await client.get("/api/v1/companies")
    assert response.status_code == 401

    response = await client.post("/api/v1/interview-sessions", json={})
    assert response.status_code == 401


async def test_regression_resume_ownership_unaffected(client: AsyncClient) -> None:
    owner_token = await _register(client, email="regress-owner@example.com")
    resume_id = await _upload_and_analyze(client, owner_token, role_key="software_engineer")

    other_token = await _register(client, email="regress-other@example.com")
    response = await client.get(f"/api/v1/resumes/{resume_id}", headers=_auth(other_token))
    assert response.status_code == 404
