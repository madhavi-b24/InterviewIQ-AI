"""GeminiResumeIntelligenceProvider — the real ResumeIntelligenceProvider
(module §8), selected whenever RESUME_INTELLIGENCE_PROVIDER=gemini (the
only non-test setting — see Settings' docstring).

Design choices, per module §8's requirements:
  - structured output: `response_schema=ExtractedProfile` (Gemini's JSON
    mode), so the SDK/model does the JSON-shape work, not a hand-rolled parser
  - low temperature (0.1): resume parsing is extraction, not creative writing
  - defensive parsing: `_parse_response` never trusts `.parsed` blindly —
    falls back to raw-text JSON, and either path re-validates through
    ExtractedProfile before anything downstream sees it
  - timeout: `asyncio.wait_for` — a hung Gemini call must not hang the
    background job forever
  - retry: exactly one retry, only for ServerError (5xx/transient) — a
    ClientError (bad key, bad request) or a validation failure retrying
    would just fail identically
  - never logs API keys or resume text — only length, for observability
"""

import asyncio
import json

from google import genai
from google.genai import types
from google.genai.errors import ClientError, ServerError
from pydantic import ValidationError

from app.core.config import Settings
from app.core.logging import get_logger
from app.services.resume_intelligence.provider import (
    ResumeIntelligenceProviderError,
    ResumeIntelligenceTimeoutError,
)
from app.services.resume_intelligence.schemas import ExtractedProfile

logger = get_logger(__name__)

_SYSTEM_INSTRUCTION = """You are the resume-parsing engine for InterviewIQ AI, an interview \
preparation platform. You extract structured, evidence-grounded information from a \
candidate's resume text. Follow these rules strictly:

1. Extract ONLY information explicitly present in the resume text provided. Never invent,
   guess, or hallucinate a name, company, skill, date, or outcome that is not in the text.
2. Every skill, project, experience, education, and certification entry MUST include an
   `evidence` field: a short verbatim or near-verbatim quote from the resume text that
   supports it. If you cannot point to supporting text for an item, do not include that item.
3. If a section (education, skills, projects, experience, certifications, achievements) has
   no content in this resume, return an empty list for it. Do not fabricate placeholder entries.
4. Copy dates exactly as written (e.g. "Jan 2022", "2021", "2019 - Present"). Do not compute,
   infer, or normalize dates yourself.
5. For skills: use source="explicit" for a skill listed in a dedicated skills/technologies
   section, source="inferred" for a skill only implied by project/experience description text.
6. Outcomes for a project must be measurable claims the candidate actually stated (e.g. a
   percentage, a count, a latency number) — never invent a plausible-sounding metric.
7. Return only the structured JSON matching the provided schema — no commentary.
"""


class GeminiResumeIntelligenceProvider:
    def __init__(self, settings: Settings) -> None:
        if not settings.GEMINI_API_KEY:
            raise ResumeIntelligenceProviderError("GEMINI_API_KEY is not configured")
        self._client = genai.Client(api_key=settings.GEMINI_API_KEY)
        self._model = settings.GEMINI_MODEL
        self._timeout_seconds = settings.RESUME_INTELLIGENCE_TIMEOUT_SECONDS

    async def extract(self, *, resume_text: str, sections: dict[str, str]) -> ExtractedProfile:
        prompt = self._build_prompt(resume_text=resume_text, sections=sections)
        logger.info(
            "resume_intelligence.gemini.request",
            resume_chars=len(resume_text),
            model=self._model,
        )

        for attempt in (1, 2):
            try:
                response = await asyncio.wait_for(
                    self._client.aio.models.generate_content(
                        model=self._model,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            system_instruction=_SYSTEM_INSTRUCTION,
                            temperature=0.1,
                            response_mime_type="application/json",
                            response_schema=ExtractedProfile,
                        ),
                    ),
                    timeout=self._timeout_seconds,
                )
                break
            except TimeoutError as exc:
                logger.warning(
                    "resume_intelligence.gemini.timeout", timeout_seconds=self._timeout_seconds
                )
                raise ResumeIntelligenceTimeoutError(
                    f"Gemini extraction timed out after {self._timeout_seconds}s"
                ) from exc
            except ServerError as exc:
                logger.warning("resume_intelligence.gemini.server_error", attempt=attempt)
                if attempt == 2:
                    raise ResumeIntelligenceProviderError(
                        f"Gemini server error after retry: {exc}"
                    ) from exc
                continue
            except ClientError as exc:
                # Bad API key, bad request, quota — retrying identically won't help.
                logger.warning("resume_intelligence.gemini.client_error")
                raise ResumeIntelligenceProviderError(f"Gemini request rejected: {exc}") from exc
            except Exception as exc:  # noqa: BLE001 — any other SDK/network failure
                logger.warning("resume_intelligence.gemini.unexpected_error", error=str(exc))
                raise ResumeIntelligenceProviderError(f"Gemini request failed: {exc}") from exc

        return self._parse_response(response)

    def _build_prompt(self, *, resume_text: str, sections: dict[str, str]) -> str:
        section_hint = "\n".join(f"- {name}" for name in sections) or "(no sections detected)"
        return (
            "Resume sections detected by a deterministic pre-pass (for context only — parse "
            "from the full text below, not just these labels):\n"
            f"{section_hint}\n\n"
            "Full resume text:\n-----\n"
            f"{resume_text}\n-----"
        )

    def _parse_response(self, response: types.GenerateContentResponse) -> ExtractedProfile:
        # google-genai populates `.parsed` with a validated instance of the
        # response_schema when it can — used first, but never trusted
        # unconditionally: a schema/SDK-version mismatch could leave it
        # None or the wrong type, so we defensively re-validate through
        # ExtractedProfile either way rather than returning `.parsed` as-is.
        parsed = getattr(response, "parsed", None)
        if parsed is not None:
            try:
                return ExtractedProfile.model_validate(parsed)
            except ValidationError:
                pass  # fall through to raw-text parsing below

        raw_text = getattr(response, "text", None)
        if not raw_text:
            raise ResumeIntelligenceProviderError("Gemini returned an empty response")
        try:
            data = json.loads(raw_text)
            return ExtractedProfile.model_validate(data)
        except (json.JSONDecodeError, ValidationError) as exc:
            raise ResumeIntelligenceProviderError(
                f"Gemini response failed schema validation: {exc}"
            ) from exc
