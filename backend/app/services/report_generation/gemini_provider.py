"""GeminiReportGenerationProvider — the real ReportGenerationProvider
(Module 7), selected whenever REPORT_GENERATION_PROVIDER=gemini. Same
shape as app/services/code_evaluation/gemini_provider.py: structured
output (`response_schema=`), low temperature, `asyncio.wait_for` timeout,
exactly one retry for `ServerError` only, defensive response parsing that
never trusts `.parsed` unconditionally.

Never asked to judge correctness or produce a score — every number in
the prompt below is already final (module §11's rule, extended here).
"""

import asyncio
import json

from google import genai
from google.genai import types
from google.genai.errors import ClientError, ServerError
from pydantic import ValidationError

from app.core.config import Settings
from app.core.logging import get_logger
from app.services.report_generation.provider import (
    AnswerEvidence,
    ReportGenerationProviderError,
    ReportGenerationTimeoutError,
)
from app.services.report_generation.schemas import ReportContentResult

logger = get_logger(__name__)

_SYSTEM_INSTRUCTION = """You are a senior technical interviewer writing the narrative sections of \
a completed candidate's interview report. Every score you are given below has ALREADY been \
computed — you are never asked about and must never contradict or restate a number as if you \
computed it yourself. Your job is ONLY to explain what the numbers mean and to identify specific, \
evidence-backed weak/strong topics and roadmap resources. Follow these rules strictly:

1. Section/overall explanations: reference the given score naturally but do not re-derive it —
   explain what it reflects about the candidate's performance in that dimension.
2. coding_explanation: leave this null if no coding evidence/score was provided — never invent
   a coding assessment for a session that had no coding round.
3. summary_text: a short, specific overall narrative — not generic praise or generic criticism.
4. weak_areas/strong_areas: topic must be a specific skill/subject (e.g. "Dynamic Programming",
   "SQL joins"), never a vague label like "technical skills". evidence_text must cite or
   paraphrase the actual evidence you were given for that topic — never fabricated. Empty lists
   are correct when there is genuinely nothing weak or nothing strong to report. Every weak_area
   and strong_area must set `section` to whichever of the five given section scores it best
   belongs to — for weak_areas this determines severity deterministically, so pick the section
   the evidence actually came from in both cases.
5. roadmap_items: one or more concrete learning resources per weak area, each with a real,
   plausible resource_title and resource_type; priority 1 is the most urgent.
6. Never comment on whether a score itself is "wrong" or should have been different — that is
   outside your role here.
7. Return only the structured JSON matching the provided schema — no commentary, no internal
   reasoning or chain-of-thought, only the conclusions.
"""


def _format_evidence(evidence: list[AnswerEvidence]) -> str:
    lines = [
        f"- [{item.round_type}/{item.dimension}] score={item.score}: {item.explanation}"
        for item in evidence
    ]
    return "\n".join(lines) if lines else "(no per-answer evidence available)"


class GeminiReportGenerationProvider:
    def __init__(self, settings: Settings) -> None:
        if not settings.GEMINI_API_KEY:
            raise ReportGenerationProviderError("GEMINI_API_KEY is not configured")
        self._client = genai.Client(api_key=settings.GEMINI_API_KEY)
        self._model = settings.GEMINI_MODEL
        self._timeout_seconds = settings.REPORT_GENERATION_TIMEOUT_SECONDS

    async def generate(
        self,
        *,
        role_title: str,
        company_name: str | None,
        section_scores: dict[str, float],
        overall_score: float,
        evidence: list[AnswerEvidence],
    ) -> ReportContentResult:
        sections_text = "\n".join(f"- {name}: {score}" for name, score in section_scores.items())
        prompt = (
            f"Role: {role_title}" + (f" at {company_name}" if company_name else "") + "\n\n"
            f"Section scores (0-100, already computed — do not recompute or restate as your own "
            f"judgment):\n{sections_text}\n\n"
            f"Overall score (0-100, already computed): {overall_score}\n\n"
            f"Per-answer evidence (already-scored explanations from the interview):\n"
            f"{_format_evidence(evidence)}"
        )
        logger.info(
            "report_generation.gemini.generate",
            role_title=role_title,
            section_count=len(section_scores),
            evidence_count=len(evidence),
        )
        for attempt in (1, 2):
            try:
                response = await asyncio.wait_for(
                    self._client.aio.models.generate_content(
                        model=self._model,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            system_instruction=_SYSTEM_INSTRUCTION,
                            temperature=0.2,
                            response_mime_type="application/json",
                            response_schema=ReportContentResult,
                        ),
                    ),
                    timeout=self._timeout_seconds,
                )
                break
            except TimeoutError as exc:
                logger.warning(
                    "report_generation.gemini.timeout", timeout_seconds=self._timeout_seconds
                )
                raise ReportGenerationTimeoutError(
                    f"Gemini call timed out after {self._timeout_seconds}s"
                ) from exc
            except ServerError as exc:
                logger.warning("report_generation.gemini.server_error", attempt=attempt)
                if attempt == 2:
                    raise ReportGenerationProviderError(
                        f"Gemini server error after retry: {exc}"
                    ) from exc
                continue
            except ClientError as exc:
                logger.warning("report_generation.gemini.client_error")
                raise ReportGenerationProviderError(f"Gemini request rejected: {exc}") from exc
            except Exception as exc:  # noqa: BLE001 — any other SDK/network failure
                logger.warning("report_generation.gemini.unexpected_error", error=str(exc))
                raise ReportGenerationProviderError(f"Gemini request failed: {exc}") from exc

        return self._parse_response(response)

    @staticmethod
    def _parse_response(response: types.GenerateContentResponse) -> ReportContentResult:
        parsed = getattr(response, "parsed", None)
        if parsed is not None:
            try:
                return ReportContentResult.model_validate(parsed)
            except ValidationError:
                pass  # fall through to raw-text parsing below

        raw_text = getattr(response, "text", None)
        if not raw_text:
            raise ReportGenerationProviderError("Gemini returned an empty response")
        try:
            data = json.loads(raw_text)
            return ReportContentResult.model_validate(data)
        except (json.JSONDecodeError, ValidationError) as exc:
            raise ReportGenerationProviderError(
                f"Gemini response failed schema validation: {exc}"
            ) from exc
