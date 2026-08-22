"""GeminiCodeEvaluationProvider — the real CodeEvaluationProvider (module
§10/§21), selected whenever CODE_EVALUATION_PROVIDER=gemini. Same shape
as app/services/interview_intelligence/gemini_provider.py: structured
output (`response_schema=`), low temperature, `asyncio.wait_for` timeout,
exactly one retry for `ServerError` only, defensive response parsing that
never trusts `.parsed` unconditionally.

Never logs source code — only its length. Never asked to judge
correctness (module §10).
"""

import asyncio
import json

from google import genai
from google.genai import types
from google.genai.errors import ClientError, ServerError
from pydantic import ValidationError

from app.core.config import Settings
from app.core.logging import get_logger
from app.services.code_evaluation.provider import (
    CodeEvaluationProviderError,
    CodeEvaluationTimeoutError,
)
from app.services.code_evaluation.schemas import CodeEvaluationResult

logger = get_logger(__name__)

_SYSTEM_INSTRUCTION = """You are a senior software engineer reviewing a candidate's final code \
submission for a technical interview coding problem. Execution has ALREADY determined \
correctness — you are never asked about and must never mention whether the tests passed or \
failed. Your job is ONLY to judge what execution cannot measure. Follow these rules strictly:

1. readability_score/explanation: naming, structure, formatting, clarity of the code as written.
2. optimization_score/explanation: how efficient the chosen approach is relative to what the
   problem actually requires — a brute-force solution that happens to pass small hidden tests is
   NOT automatically well-optimized.
3. edge_case_score/explanation: judge this from reading the code's own logic (does it handle
   empty input, single-element input, duplicates, boundary values, negative numbers where
   relevant?) — not from which hidden tests were or weren't included.
4. time_complexity/space_complexity: your own Big-O estimate of the submitted approach, e.g.
   'O(n log n)' / 'O(n)' — a short descriptive string, not a score.
5. strengths/weaknesses/recommendations: concrete and specific to THIS submission. Empty lists
   are correct when there is nothing notable — never invent an entry to fill a list.
6. Never comment on whether the solution is "correct" or how many tests it passed — that is
   determined by execution, not by you, and is outside your role here.
7. Return only the structured JSON matching the provided schema — no commentary, no internal
   reasoning or chain-of-thought, only the conclusions.
"""


class GeminiCodeEvaluationProvider:
    def __init__(self, settings: Settings) -> None:
        if not settings.GEMINI_API_KEY:
            raise CodeEvaluationProviderError("GEMINI_API_KEY is not configured")
        self._client = genai.Client(api_key=settings.GEMINI_API_KEY)
        self._model = settings.GEMINI_MODEL
        self._timeout_seconds = settings.CODE_EVALUATION_TIMEOUT_SECONDS

    async def evaluate(
        self,
        *,
        problem_title: str,
        problem_description: str,
        language: str,
        source_code: str,
        passed_test_count: int,
        total_test_count: int,
    ) -> CodeEvaluationResult:
        prompt = (
            f"Problem: {problem_title}\n{problem_description}\n\n"
            f"Language: {language}\n"
            f"Test results (already determined by execution, for context only — "
            f"do not comment on this number): {passed_test_count}/{total_test_count} passed\n\n"
            f"Submitted code:\n{source_code}"
        )
        logger.info(
            "code_evaluation.gemini.evaluate",
            language=language,
            source_chars=len(source_code),
            passed_test_count=passed_test_count,
            total_test_count=total_test_count,
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
                            response_schema=CodeEvaluationResult,
                        ),
                    ),
                    timeout=self._timeout_seconds,
                )
                break
            except TimeoutError as exc:
                logger.warning(
                    "code_evaluation.gemini.timeout", timeout_seconds=self._timeout_seconds
                )
                raise CodeEvaluationTimeoutError(
                    f"Gemini call timed out after {self._timeout_seconds}s"
                ) from exc
            except ServerError as exc:
                logger.warning("code_evaluation.gemini.server_error", attempt=attempt)
                if attempt == 2:
                    raise CodeEvaluationProviderError(
                        f"Gemini server error after retry: {exc}"
                    ) from exc
                continue
            except ClientError as exc:
                logger.warning("code_evaluation.gemini.client_error")
                raise CodeEvaluationProviderError(f"Gemini request rejected: {exc}") from exc
            except Exception as exc:  # noqa: BLE001 — any other SDK/network failure
                logger.warning("code_evaluation.gemini.unexpected_error", error=str(exc))
                raise CodeEvaluationProviderError(f"Gemini request failed: {exc}") from exc

        return self._parse_response(response)

    @staticmethod
    def _parse_response(response: types.GenerateContentResponse) -> CodeEvaluationResult:
        parsed = getattr(response, "parsed", None)
        if parsed is not None:
            try:
                return CodeEvaluationResult.model_validate(parsed)
            except ValidationError:
                pass  # fall through to raw-text parsing below

        raw_text = getattr(response, "text", None)
        if not raw_text:
            raise CodeEvaluationProviderError("Gemini returned an empty response")
        try:
            data = json.loads(raw_text)
            return CodeEvaluationResult.model_validate(data)
        except (json.JSONDecodeError, ValidationError) as exc:
            raise CodeEvaluationProviderError(
                f"Gemini response failed schema validation: {exc}"
            ) from exc
