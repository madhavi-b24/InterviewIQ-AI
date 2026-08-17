"""Regression coverage for Gemini structured-output schema compatibility.

`FakeResumeIntelligenceProvider` (used by every other resume test) never
goes through the real `google-genai` SDK's schema conversion, so it cannot
catch a Pydantic field default that Gemini's structured-output mode
rejects — see `app/services/resume_intelligence/schemas.py`'s "Gemini
structured-output constraint" note for the exact rule
(`ExtractedSkill.source`'s `default="explicit"` was the bug: it produced
`"default": "explicit"` in the generated JSON schema, and google-genai's
client-side schema converter raises `ValueError("Default value is not
supported in the response schema for the Gemini API.")` for any
non-null default anywhere in a `response_schema`).

These tests exercise the real SDK code path `models.generate_content`
calls internally to build every request — no network call, no valid API
key required (a syntactically well-formed dummy key is enough to
construct a client and run its local schema conversion), so they fail
immediately and deterministically if this class of bug is reintroduced.
"""

import pytest
from google import genai
from google.genai import _transformers as genai_transformers

from app.services.resume_intelligence.schemas import ExtractedProfile


def _find_non_null_defaults(node: object, path: str = "$") -> list[str]:
    """Walks a JSON-schema dict/list and returns every path carrying a
    non-null "default" key — precisely what google-genai's schema
    converter rejects for a Gemini `response_schema`.
    """
    hits: list[str] = []
    if isinstance(node, dict):
        if "default" in node and node["default"] is not None:
            hits.append(f"{path}: default={node['default']!r}")
        for key, value in node.items():
            hits.extend(_find_non_null_defaults(value, f"{path}.{key}"))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            hits.extend(_find_non_null_defaults(value, f"{path}[{index}]"))
    return hits


def test_extracted_profile_schema_has_no_non_null_defaults() -> None:
    """Would have failed before the fix — `ExtractedSkill.source`'s
    `default="explicit"` was the only non-null default anywhere in the
    schema tree Gemini receives.
    """
    schema = ExtractedProfile.model_json_schema()
    hits = _find_non_null_defaults(schema)
    assert hits == [], f"non-null default(s) present in Gemini response_schema: {hits}"


def test_extracted_profile_survives_gemini_sdk_schema_conversion() -> None:
    """Exercises the exact `google-genai` SDK function
    (`_transformers.t_schema`) that `models.generate_content` calls
    internally to convert `response_schema=ExtractedProfile` before
    issuing any network request — this *is* the code path
    `GeminiResumeIntelligenceProvider.extract()` goes through in
    production, just invoked directly here without a real API call.
    """
    client = genai.Client(api_key="dummy-key-for-schema-conversion-check-only")
    try:
        schema = genai_transformers.t_schema(client, ExtractedProfile)
    except ValueError as exc:
        pytest.fail(f"ExtractedProfile failed Gemini's schema conversion: {exc}")
    assert schema is not None
