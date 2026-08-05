"""Resume Intelligence tests — module §19.

The background resume-processing job runs synchronously as part of
Starlette's response cycle under ASGITransport (no real network hop), so
by the time `await client.post("/api/v1/resumes", ...)` returns, the
whole pipeline (extraction -> section detection -> fake LLM extraction ->
persistence -> best-effort embedding) has already completed and
`parsed_status` is already a terminal value (done/failed) — no polling
needed in these tests. RESUME_INTELLIGENCE_PROVIDER=fake /
RESUME_EMBEDDING_PROVIDER=fake (.env.test) make this deterministic and
network-free; see app/services/resume_intelligence/fake_provider.py.
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.db.session import get_session_factory
from app.models.resume import Resume
from app.services.resume.role_profiles import available_role_keys
from app.services.resume.skill_normalization import normalize_skill
from app.services.resume_intelligence.fake_provider import get_fake_resume_intelligence_provider
from tests.pdf_fixtures import (
    EMPTY_BYTES,
    TRUNCATED_PDF_BYTES,
    WRONG_SIGNATURE_BYTES,
    blank_pdf,
    build_minimal_pdf,
    fictional_resume_pdf,
)

VALID_PASSWORD = "correct-horse-42"


# --- helpers -------------------------------------------------------------


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


async def _upload(
    client: AsyncClient,
    token: str,
    content: bytes,
    *,
    filename: str = "resume.pdf",
    content_type: str | None = "application/pdf",
):
    return await client.post(
        "/api/v1/resumes",
        headers=_auth(token),
        files={"file": (filename, content, content_type)},
    )


async def _upload_ok(client: AsyncClient, token: str, content: bytes, **kwargs) -> dict:
    response = await _upload(client, token, content, **kwargs)
    assert response.status_code == 201, response.text
    return response.json()


async def _get_resume(client: AsyncClient, token: str, resume_id: str) -> dict:
    """POST /resumes always returns parsed_status="pending" — the upload
    response is deliberately returned before the background job runs
    (API.md: "GET /resumes/{id} is the poll target until parsed_status
    = done"). Tests that need the final state re-fetch through this
    helper rather than reading the upload response's parsed_status.
    """
    response = await client.get(f"/api/v1/resumes/{resume_id}", headers=_auth(token))
    assert response.status_code == 200, response.text
    return response.json()


async def _fetch_resume_row(resume_id: str) -> Resume:
    async with get_session_factory()() as session:
        result = await session.execute(select(Resume).where(Resume.id == uuid.UUID(resume_id)))
        return result.scalar_one()


# ===========================================================================
# UPLOAD
# ===========================================================================


async def test_upload_valid_pdf_success(client: AsyncClient) -> None:
    token = await _register(client, email="upload-ok@example.com")
    body = await _upload_ok(client, token, fictional_resume_pdf())

    assert body["original_filename"] == "resume.pdf"
    assert body["is_active"] is True
    # Upload returns immediately with pending — processing happens via the
    # Job Runner, not inline in the request (API.md §2).
    assert body["parsed_status"] == "pending"
    assert body["processing_error"] is None

    settled = await _get_resume(client, token, body["id"])
    assert settled["parsed_status"] == "done"
    assert settled["processing_error"] is None


async def test_upload_requires_authentication(client: AsyncClient) -> None:
    response = await _upload(client, "not-a-real-token", fictional_resume_pdf())
    assert response.status_code == 401


async def test_upload_unauthenticated_no_header(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/resumes", files={"file": ("resume.pdf", fictional_resume_pdf(), "application/pdf")}
    )
    assert response.status_code == 401


async def test_upload_wrong_extension(client: AsyncClient) -> None:
    token = await _register(client, email="wrong-ext@example.com")
    response = await _upload(client, token, fictional_resume_pdf(), filename="resume.docx")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "UNSUPPORTED_FILE_TYPE"


async def test_upload_wrong_mime_type(client: AsyncClient) -> None:
    token = await _register(client, email="wrong-mime@example.com")
    response = await _upload(client, token, fictional_resume_pdf(), content_type="image/png")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "UNSUPPORTED_MIME_TYPE"


async def test_upload_invalid_pdf_signature(client: AsyncClient) -> None:
    token = await _register(client, email="bad-signature@example.com")
    response = await _upload(client, token, WRONG_SIGNATURE_BYTES)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_PDF_SIGNATURE"


async def test_upload_malformed_pdf(client: AsyncClient) -> None:
    token = await _register(client, email="malformed@example.com")
    response = await _upload(client, token, TRUNCATED_PDF_BYTES)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "MALFORMED_PDF"


async def test_upload_empty_file(client: AsyncClient) -> None:
    token = await _register(client, email="empty-file@example.com")
    response = await _upload(client, token, EMPTY_BYTES)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "EMPTY_FILE"


async def test_upload_oversized_file(client: AsyncClient) -> None:
    token = await _register(client, email="oversized@example.com")
    # Default RESUME_MAX_UPLOAD_MB=5 — size check runs before signature
    # validation (app/services/resume/pdf.py), so garbage content is fine.
    oversized = b"0" * (6 * 1024 * 1024)
    response = await _upload(client, token, oversized)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "FILE_TOO_LARGE"


# ===========================================================================
# OWNERSHIP
# ===========================================================================


async def test_user_can_retrieve_own_resume(client: AsyncClient) -> None:
    token = await _register(client, email="owner@example.com")
    uploaded = await _upload_ok(client, token, fictional_resume_pdf())

    response = await client.get(f"/api/v1/resumes/{uploaded['id']}", headers=_auth(token))
    assert response.status_code == 200
    assert response.json()["id"] == uploaded["id"]


async def test_user_cannot_retrieve_another_users_resume(client: AsyncClient) -> None:
    owner_token = await _register(client, email="victim@example.com")
    attacker_token = await _register(client, email="attacker@example.com")
    uploaded = await _upload_ok(client, owner_token, fictional_resume_pdf())

    response = await client.get(f"/api/v1/resumes/{uploaded['id']}", headers=_auth(attacker_token))
    assert response.status_code == 404

    response = await client.get(
        f"/api/v1/resumes/{uploaded['id']}/analysis", headers=_auth(attacker_token)
    )
    assert response.status_code == 404


async def test_user_cannot_delete_another_users_resume(client: AsyncClient) -> None:
    owner_token = await _register(client, email="victim2@example.com")
    attacker_token = await _register(client, email="attacker2@example.com")
    uploaded = await _upload_ok(client, owner_token, fictional_resume_pdf())

    response = await client.delete(
        f"/api/v1/resumes/{uploaded['id']}", headers=_auth(attacker_token)
    )
    assert response.status_code == 404

    # Original owner can still retrieve it — the attacker's attempt did nothing.
    response = await client.get(f"/api/v1/resumes/{uploaded['id']}", headers=_auth(owner_token))
    assert response.status_code == 200


async def test_list_resumes_only_shows_own(client: AsyncClient) -> None:
    token_a = await _register(client, email="lister-a@example.com")
    token_b = await _register(client, email="lister-b@example.com")
    await _upload_ok(client, token_a, fictional_resume_pdf())

    response = await client.get("/api/v1/resumes", headers=_auth(token_b))
    assert response.status_code == 200
    assert response.json() == []


# ===========================================================================
# EXTRACTION
# ===========================================================================


async def test_text_extraction_completes_and_persists_raw_text(client: AsyncClient) -> None:
    token = await _register(client, email="extract@example.com")
    uploaded = await _upload_ok(client, token, fictional_resume_pdf())

    resume = await _fetch_resume_row(uploaded["id"])
    assert resume.parsed_status.value == "done"
    assert resume.raw_text and "Alex Rivera" in resume.raw_text


async def test_multi_page_pdf_extracted_across_pages(client: AsyncClient) -> None:
    token = await _register(client, email="multipage@example.com")
    # fictional_resume_pdf() splits content across two pages — content
    # from the second page (skills/experience) must still be extracted.
    uploaded = await _upload_ok(client, token, fictional_resume_pdf())
    resume = await _fetch_resume_row(uploaded["id"])
    assert "SKILLS" in resume.raw_text
    assert "EXPERIENCE" in resume.raw_text


async def test_scanned_pdf_marks_failed_with_ocr_guidance(client: AsyncClient) -> None:
    token = await _register(client, email="scanned@example.com")
    uploaded = await _upload_ok(client, token, blank_pdf())

    settled = await _get_resume(client, token, uploaded["id"])
    assert settled["parsed_status"] == "failed"
    assert "ocr" in settled["processing_error"].lower()


async def test_section_detection_finds_expected_sections(client: AsyncClient) -> None:
    token = await _register(client, email="sections@example.com")
    uploaded = await _upload_ok(client, token, fictional_resume_pdf())

    response = await client.get(f"/api/v1/resumes/{uploaded['id']}/analysis", headers=_auth(token))
    detected = set(response.json()["detected_sections"])
    assert {
        "summary",
        "skills",
        "experience",
        "projects",
        "certifications",
        "achievements",
    } <= detected


# ===========================================================================
# STRUCTURED ANALYSIS
# ===========================================================================


async def test_valid_structured_response_has_evidence(client: AsyncClient) -> None:
    token = await _register(client, email="structured@example.com")
    uploaded = await _upload_ok(client, token, fictional_resume_pdf())

    response = await client.get(f"/api/v1/resumes/{uploaded['id']}/analysis", headers=_auth(token))
    body = response.json()
    assert body["parsed_status"] == "done"
    assert len(body["skills"]) > 0
    assert all(skill["evidence"] for skill in body["skills"])
    assert len(body["projects"]) > 0
    assert body["projects"][0]["evidence"]


async def test_missing_sections_return_empty_lists_not_error(client: AsyncClient) -> None:
    token = await _register(client, email="sparse@example.com")
    sparse_pdf = build_minimal_pdf(
        [["Jordan Lee", "SUMMARY", "A candidate with no listed skills."]]
    )
    uploaded = await _upload_ok(client, token, sparse_pdf)

    response = await client.get(f"/api/v1/resumes/{uploaded['id']}/analysis", headers=_auth(token))
    assert response.status_code == 200
    body = response.json()
    assert body["skills"] == []
    assert body["projects"] == []
    assert body["certifications"] == []


async def test_llm_malformed_response_preserves_raw_text(client: AsyncClient) -> None:
    get_fake_resume_intelligence_provider().malformed = True
    token = await _register(client, email="llm-malformed@example.com")
    uploaded = await _upload_ok(client, token, fictional_resume_pdf())

    settled = await _get_resume(client, token, uploaded["id"])
    assert settled["parsed_status"] == "failed"
    assert "ai analysis failed" in settled["processing_error"].lower()
    resume = await _fetch_resume_row(uploaded["id"])
    # Deterministic extraction from step 2 must survive the AI failure.
    assert resume.raw_text and "Alex Rivera" in resume.raw_text
    assert resume.detected_sections


async def test_llm_timeout_marks_failed(client: AsyncClient) -> None:
    get_fake_resume_intelligence_provider().timeout = True
    token = await _register(client, email="llm-timeout@example.com")
    uploaded = await _upload_ok(client, token, fictional_resume_pdf())

    settled = await _get_resume(client, token, uploaded["id"])
    assert settled["parsed_status"] == "failed"
    assert (
        "timeout" in settled["processing_error"].lower()
        or "timed out" in settled["processing_error"].lower()
    )


async def test_llm_provider_failure_marks_failed(client: AsyncClient) -> None:
    get_fake_resume_intelligence_provider().fail = True
    token = await _register(client, email="llm-fail@example.com")
    uploaded = await _upload_ok(client, token, fictional_resume_pdf())

    settled = await _get_resume(client, token, uploaded["id"])
    assert settled["parsed_status"] == "failed"
    assert settled["processing_error"]


async def test_no_hallucinated_skills(client: AsyncClient) -> None:
    """Every persisted skill's raw (pre-normalization) text must actually
    appear in the resume's own Skills section — the fake provider only
    ever extracts what's literally there, and normalize_skill() never
    invents a canonical form for unmatched input either.
    """
    token = await _register(client, email="no-hallucination@example.com")
    uploaded = await _upload_ok(client, token, fictional_resume_pdf())

    response = await client.get(f"/api/v1/resumes/{uploaded['id']}/analysis", headers=_auth(token))
    resume = await _fetch_resume_row(uploaded["id"])
    skills_section_text = resume.detected_sections.get("skills", "").lower()
    for skill in response.json()["skills"]:
        assert skill["raw_text"].lower() in skills_section_text


# ===========================================================================
# SKILLS
# ===========================================================================


@pytest.mark.parametrize(
    ("raw", "expected_canonical"),
    [
        ("JS", "JavaScript"),
        ("Postgres", "PostgreSQL"),
        ("Fast API", "FastAPI"),
        ("Node.js", "Node.js"),
    ],
)
def test_skill_normalization_aliases(raw: str, expected_canonical: str) -> None:
    result = normalize_skill(raw)
    assert result.canonical == expected_canonical
    assert result.matched is True


def test_skill_normalization_unmatched_skill_not_invented() -> None:
    result = normalize_skill("SomeBespokeInternalTool")
    assert result.canonical == "SomeBespokeInternalTool"
    assert result.matched is False
    assert result.category.value == "other"


def test_skill_category_mapping() -> None:
    assert normalize_skill("Python").category.value == "programming_language"
    assert normalize_skill("Postgres").category.value == "database"
    assert normalize_skill("AWS").category.value == "cloud"
    assert normalize_skill("PyTorch").category.value == "ai_ml"
    assert normalize_skill("Git").category.value == "developer_tool"


async def test_skill_normalization_end_to_end_via_upload(client: AsyncClient) -> None:
    token = await _register(client, email="skill-e2e@example.com")
    uploaded = await _upload_ok(client, token, fictional_resume_pdf())

    response = await client.get(f"/api/v1/resumes/{uploaded['id']}/analysis", headers=_auth(token))
    names = {skill["name"] for skill in response.json()["skills"]}
    assert "PostgreSQL" in names  # resume text says "Postgres"
    assert "JavaScript" in names  # resume text says "JS"


# ===========================================================================
# VERSIONING
# ===========================================================================


async def test_multiple_uploads_create_history(client: AsyncClient) -> None:
    token = await _register(client, email="versioning@example.com")
    await _upload_ok(client, token, fictional_resume_pdf())
    await _upload_ok(client, token, fictional_resume_pdf())

    response = await client.get("/api/v1/resumes", headers=_auth(token))
    assert len(response.json()) == 2


async def test_only_latest_resume_is_active(client: AsyncClient) -> None:
    token = await _register(client, email="active-flag@example.com")
    first = await _upload_ok(client, token, fictional_resume_pdf())
    second = await _upload_ok(client, token, fictional_resume_pdf())

    response = await client.get("/api/v1/resumes", headers=_auth(token))
    by_id = {item["id"]: item for item in response.json()}
    assert by_id[second["id"]]["is_active"] is True
    assert by_id[first["id"]]["is_active"] is False


async def test_historical_resume_analysis_preserved_after_new_upload(client: AsyncClient) -> None:
    token = await _register(client, email="history-preserved@example.com")
    first = await _upload_ok(client, token, fictional_resume_pdf())
    await _upload_ok(client, token, fictional_resume_pdf())

    response = await client.get(f"/api/v1/resumes/{first['id']}/analysis", headers=_auth(token))
    assert response.status_code == 200
    assert response.json()["skills"]  # still fully queryable, not wiped


async def test_delete_active_resume_promotes_next_most_recent(client: AsyncClient) -> None:
    token = await _register(client, email="promote@example.com")
    first = await _upload_ok(client, token, fictional_resume_pdf())
    second = await _upload_ok(client, token, fictional_resume_pdf())

    delete_response = await client.delete(f"/api/v1/resumes/{second['id']}", headers=_auth(token))
    assert delete_response.status_code == 204

    response = await client.get(f"/api/v1/resumes/{first['id']}", headers=_auth(token))
    assert response.json()["is_active"] is True


# ===========================================================================
# READINESS
# ===========================================================================


async def test_role_readiness_matching_and_missing_skills(client: AsyncClient) -> None:
    token = await _register(client, email="readiness@example.com")
    uploaded = await _upload_ok(client, token, fictional_resume_pdf())

    response = await client.post(
        f"/api/v1/resumes/{uploaded['id']}/gap-analysis",
        headers=_auth(token),
        json={"role_key": "backend_engineer"},
    )
    assert response.status_code == 200
    body = response.json()
    assert "PostgreSQL" in body["matching_skills"]
    assert set(body["missing_skills"]) <= {
        "Python",
        "Java",
        "Node.js",
        "SQL",
        "PostgreSQL",
        "REST APIs",
        "Git",
    }


async def test_role_readiness_explainable_difficulty(client: AsyncClient) -> None:
    token = await _register(client, email="difficulty@example.com")
    uploaded = await _upload_ok(client, token, fictional_resume_pdf())

    response = await client.post(
        f"/api/v1/resumes/{uploaded['id']}/gap-analysis",
        headers=_auth(token),
        json={"role_key": "backend_engineer"},
    )
    body = response.json()
    assert body["recommended_difficulty"] in {"easy", "medium", "hard"}
    assert body["recommended_level_label"] in {"Beginner", "Intermediate", "Advanced"}
    assert 0 <= body["confidence"] <= 100
    assert len(body["reasons"]) >= 2  # explainable — multiple concrete signals, not one bare number


async def test_role_readiness_unknown_role_key(client: AsyncClient) -> None:
    token = await _register(client, email="unknown-role@example.com")
    uploaded = await _upload_ok(client, token, fictional_resume_pdf())

    response = await client.post(
        f"/api/v1/resumes/{uploaded['id']}/gap-analysis",
        headers=_auth(token),
        json={"role_key": "underwater_basket_weaver"},
    )
    assert response.status_code == 404
    assert response.json()["error"]["details"]["available_role_keys"] == available_role_keys()


async def test_role_readiness_requires_completed_analysis(client: AsyncClient) -> None:
    get_fake_resume_intelligence_provider().fail = True
    token = await _register(client, email="not-ready@example.com")
    uploaded = await _upload_ok(client, token, fictional_resume_pdf())
    settled = await _get_resume(client, token, uploaded["id"])
    assert settled["parsed_status"] == "failed"

    response = await client.post(
        f"/api/v1/resumes/{uploaded['id']}/gap-analysis",
        headers=_auth(token),
        json={"role_key": "backend_engineer"},
    )
    assert response.status_code == 409


async def test_role_readiness_replaces_single_row_on_recall(client: AsyncClient) -> None:
    """resume_gap_analysis is at most one row per resume (Database.md's ER
    diagram) — calling gap-analysis twice with different roles must
    replace, not accumulate.
    """
    token = await _register(client, email="gap-replace@example.com")
    uploaded = await _upload_ok(client, token, fictional_resume_pdf())

    await client.post(
        f"/api/v1/resumes/{uploaded['id']}/gap-analysis",
        headers=_auth(token),
        json={"role_key": "backend_engineer"},
    )
    second = await client.post(
        f"/api/v1/resumes/{uploaded['id']}/gap-analysis",
        headers=_auth(token),
        json={"role_key": "ai_engineer"},
    )
    assert second.json()["role_key"] == "ai_engineer"

    async with get_session_factory()() as session:
        from app.models.resume import ResumeGapAnalysis

        result = await session.execute(
            select(ResumeGapAnalysis).where(
                ResumeGapAnalysis.resume_id == uuid.UUID(uploaded["id"])
            )
        )
        rows = result.scalars().all()
        assert len(rows) == 1
        assert rows[0].role_key == "ai_engineer"


# ===========================================================================
# SECURITY
# ===========================================================================


async def test_filename_traversal_attempt_is_sanitized(client: AsyncClient) -> None:
    token = await _register(client, email="traversal@example.com")
    body = await _upload_ok(
        client, token, fictional_resume_pdf(), filename="../../../../etc/passwd.pdf"
    )
    assert "/" not in body["original_filename"]
    assert ".." not in body["original_filename"]
    assert body["original_filename"] == "passwd.pdf"


async def test_filename_traversal_backslash_variant_is_sanitized(client: AsyncClient) -> None:
    token = await _register(client, email="traversal-win@example.com")
    body = await _upload_ok(
        client, token, fictional_resume_pdf(), filename="..\\..\\windows\\system32\\evil.pdf"
    )
    assert "\\" not in body["original_filename"]
    assert body["original_filename"] == "evil.pdf"


async def test_unauthorized_list_and_get_rejected(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/resumes")).status_code == 401
    assert (await client.get(f"/api/v1/resumes/{uuid.uuid4()}")).status_code == 401


async def test_cross_user_access_denied_on_every_endpoint(client: AsyncClient) -> None:
    owner_token = await _register(client, email="cross-owner@example.com")
    attacker_token = await _register(client, email="cross-attacker@example.com")
    uploaded = await _upload_ok(client, owner_token, fictional_resume_pdf())
    resume_id = uploaded["id"]

    assert (
        await client.get(f"/api/v1/resumes/{resume_id}", headers=_auth(attacker_token))
    ).status_code == 404
    assert (
        await client.get(f"/api/v1/resumes/{resume_id}/analysis", headers=_auth(attacker_token))
    ).status_code == 404
    assert (
        await client.post(
            f"/api/v1/resumes/{resume_id}/gap-analysis",
            headers=_auth(attacker_token),
            json={"role_key": "backend_engineer"},
        )
    ).status_code == 404
    assert (
        await client.delete(f"/api/v1/resumes/{resume_id}", headers=_auth(attacker_token))
    ).status_code == 404


async def test_nonexistent_resume_id_returns_404_not_500(client: AsyncClient) -> None:
    token = await _register(client, email="nonexistent@example.com")
    response = await client.get(f"/api/v1/resumes/{uuid.uuid4()}", headers=_auth(token))
    assert response.status_code == 404
