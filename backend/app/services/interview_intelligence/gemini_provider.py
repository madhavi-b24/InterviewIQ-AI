"""GeminiInterviewAgentProvider — the real InterviewAgentProvider (module
§21), selected whenever INTERVIEW_ENGINE_PROVIDER=gemini (the only
non-test setting — see Settings' docstring).

Design choices, mirroring app/services/resume_intelligence/gemini_provider.py
exactly (module §21's explicit instruction: use the existing Gemini
provider abstraction, don't scatter SDK calls, use structured Pydantic
outputs validated on every response):
  - structured output: `response_schema=<Model>` per call, so the SDK/model
    does the JSON-shape work, not a hand-rolled parser
  - low temperature (0.2): evaluation/question generation should be
    consistent, not creative-writing; slightly higher than Resume
    Intelligence's 0.1 since question phrasing benefits from a little more
    variety than fact extraction does
  - defensive parsing: never trusts `.parsed` blindly — falls back to
    raw-text JSON, and either path re-validates through the target schema
  - timeout: `asyncio.wait_for` — a hung Gemini call must not hang the
    request forever (module §22)
  - retry: exactly one retry, only for ServerError (5xx/transient) — a
    ClientError (bad key, bad request) or a validation failure retrying
    would just fail identically (module §22)
  - never logs API keys, resume text, or full question/answer text — only
    lengths, for observability (module §20's "no hidden reasoning
    exposure" extends to logs, not just API responses)
"""

import asyncio
import json
from typing import TypeVar

from google import genai
from google.genai import types
from google.genai.errors import ClientError, ServerError
from pydantic import BaseModel, ValidationError

from app.core.config import Settings
from app.core.logging import get_logger
from app.services.interview_intelligence.provider import (
    InterviewIntelligenceProviderError,
    InterviewIntelligenceTimeoutError,
)
from app.services.interview_intelligence.schemas import (
    CommunicationEvaluation,
    GeneratedQuestion,
    TechnicalEvaluation,
)

logger = get_logger(__name__)

_SchemaT = TypeVar("_SchemaT", bound=BaseModel)

_QUESTION_SYSTEM_INSTRUCTION = """You are an experienced technical interviewer for InterviewIQ AI, \
an interview preparation platform. You ask ONE clear, realistic interview question at a time, in a \
natural interviewer voice. Follow these rules strictly:

1. Ask exactly ONE primary question — never a list of questions, never multiple questions joined
   together.
2. Match the stated difficulty and round type. Do not ask a coding-implementation question in a
   behavioral round, or vice versa.
3. Never repeat or closely rephrase any question in the "already asked" list provided.
4. If resume evidence (skills/projects/evidence snippets) is provided, you may ask about it — but
   ONLY about what is explicitly present in that evidence. Never assert or ask about a technology,
   deployment target, or outcome that isn't in the provided evidence (e.g. do not ask "you deployed
   it to Kubernetes" unless the evidence actually says so). Set grounded_in_resume=true only when
   you do this.
5. If no resume evidence is provided, or you are not asking about it, ask a role-appropriate
   general question and set grounded_in_resume=false.
6. Keep the question concise — one to three sentences, no long preamble.
7. Return only the structured JSON matching the provided schema — no commentary, no explanation of
   your own reasoning.
"""

_FOLLOW_UP_SYSTEM_INSTRUCTION = """You are an experienced technical interviewer for InterviewIQ \
AI. The candidate just answered your previous question, and you have a specific, concrete reason \
to probe deeper. Ask ONE natural follow-up question that directly targets that reason. Follow \
these rules strictly:

1. Ask exactly ONE follow-up question, grounded in what the candidate actually said in their answer
   — quote or reference their own words/claims where natural, the way a real interviewer would.
2. Stay tightly scoped to the stated follow-up reason — do not pivot to an unrelated topic.
3. Keep it concise, in a natural interviewer voice, one to two sentences.
4. Return only the structured JSON matching the provided schema — no commentary.
"""

_TECHNICAL_EVAL_SYSTEM_INSTRUCTION = """You are the technical evaluator for InterviewIQ AI, an \
interview preparation platform. Given an interview question and the candidate's answer, score \
technical correctness and problem-solving quality. Follow these rules strictly:

1. Scores are 0-100. Base them only on what the candidate actually wrote — never give credit for
   claims they did not make, and never penalize for something they were not asked about.
2. Every score MUST be paired with a concise, specific explanation citing what the candidate said —
   never a bare number, never generic praise/criticism.
3. missing_concepts/strengths/weaknesses must be concrete and specific to this answer, not generic
   interview advice. Empty lists are correct when there is nothing notable to report — never
   fabricate an entry to fill a list.
4. Set follow_up_worthy=true ONLY when there is one specific, concrete reason to probe deeper on
   this exact answer (an incomplete claim, an interesting or incorrect claim worth testing, a
   shallow explanation) — not simply because the answer could theoretically be longer. If true,
   follow_up_reason must name that specific reason in one short sentence.
5. Use any provided knowledge/grounding context to check technical claims, but do not treat it as
   the only possible correct answer — multiple valid approaches can both score well.
6. Return only the structured JSON matching the provided schema — no commentary, no internal
   reasoning or chain-of-thought, only the conclusions.
"""

_COMMUNICATION_EVAL_SYSTEM_INSTRUCTION = """You are the communication evaluator for InterviewIQ \
AI. Given an interview question and the candidate's answer, score ONLY observable communication \
qualities. Follow these rules strictly:

1. Score communication: clarity, structure, conciseness, terminology usage, and ability to explain
   reasoning — based only on the text itself.
2. Score confidence as the observable directness/assertiveness of the candidate's PHRASING ONLY
   (e.g. hedging language like "I think maybe" vs. decisive, direct explanation). This is NOT a
   judgment of the candidate's psychological state, personality, gender, or how they actually feel —
   never infer or mention anything beyond word choice and sentence structure.
3. Do not let technical correctness influence these scores — a technically wrong but clearly and
   confidently explained answer can still score well here, and vice versa.
4. Every score MUST be paired with a concise, specific explanation citing the candidate's actual
   phrasing — never a bare number.
5. Return only the structured JSON matching the provided schema — no commentary.
"""


class GeminiInterviewAgentProvider:
    def __init__(self, settings: Settings) -> None:
        if not settings.GEMINI_API_KEY:
            raise InterviewIntelligenceProviderError("GEMINI_API_KEY is not configured")
        self._client = genai.Client(api_key=settings.GEMINI_API_KEY)
        self._model = settings.GEMINI_MODEL
        self._timeout_seconds = settings.INTERVIEW_ENGINE_TIMEOUT_SECONDS

    async def generate_question(
        self,
        *,
        role_title: str,
        round_type: str,
        difficulty: str,
        skills: list[str],
        evidence_snippets: list[str],
        asked_questions: list[str],
        knowledge_context: str,
    ) -> GeneratedQuestion:
        prompt = (
            f"Role: {role_title}\nRound type: {round_type}\nDifficulty: {difficulty}\n\n"
            f"Resume skills evidenced: {', '.join(skills) or '(none provided)'}\n"
            f"Resume evidence snippets:\n"
            + ("\n".join(f"- {s}" for s in evidence_snippets) or "(none provided)")
            + f"\n\nKnowledge/grounding context:\n{knowledge_context or '(none)'}\n\n"
            "Already-asked questions this session (never repeat/closely rephrase these):\n"
            + ("\n".join(f"- {q}" for q in asked_questions) or "(none yet)")
        )
        logger.info(
            "interview_intelligence.gemini.generate_question",
            round_type=round_type,
            difficulty=difficulty,
            asked_count=len(asked_questions),
        )
        return await self._call(
            prompt=prompt,
            system_instruction=_QUESTION_SYSTEM_INSTRUCTION,
            response_schema=GeneratedQuestion,
        )

    async def generate_follow_up(
        self,
        *,
        role_title: str,
        round_type: str,
        difficulty: str,
        previous_question: str,
        previous_answer: str,
        follow_up_reason: str,
        knowledge_context: str,
    ) -> GeneratedQuestion:
        prompt = (
            f"Role: {role_title}\nRound type: {round_type}\nDifficulty: {difficulty}\n\n"
            f"Previous question: {previous_question}\n"
            f"Candidate's answer: {previous_answer}\n\n"
            f"Reason to follow up: {follow_up_reason}\n\n"
            f"Knowledge/grounding context:\n{knowledge_context or '(none)'}"
        )
        logger.info(
            "interview_intelligence.gemini.generate_follow_up",
            round_type=round_type,
            difficulty=difficulty,
            answer_chars=len(previous_answer),
        )
        return await self._call(
            prompt=prompt,
            system_instruction=_FOLLOW_UP_SYSTEM_INSTRUCTION,
            response_schema=GeneratedQuestion,
        )

    async def evaluate_technical(
        self,
        *,
        question_text: str,
        answer_text: str,
        round_type: str,
        difficulty: str,
        knowledge_context: str,
    ) -> TechnicalEvaluation:
        prompt = (
            f"Round type: {round_type}\nDifficulty: {difficulty}\n\n"
            f"Question: {question_text}\n"
            f"Candidate's answer: {answer_text}\n\n"
            f"Knowledge/grounding context:\n{knowledge_context or '(none)'}"
        )
        logger.info(
            "interview_intelligence.gemini.evaluate_technical",
            round_type=round_type,
            difficulty=difficulty,
            answer_chars=len(answer_text),
        )
        return await self._call(
            prompt=prompt,
            system_instruction=_TECHNICAL_EVAL_SYSTEM_INSTRUCTION,
            response_schema=TechnicalEvaluation,
        )

    async def evaluate_communication(
        self, *, question_text: str, answer_text: str
    ) -> CommunicationEvaluation:
        prompt = f"Question: {question_text}\nCandidate's answer: {answer_text}"
        logger.info(
            "interview_intelligence.gemini.evaluate_communication", answer_chars=len(answer_text)
        )
        return await self._call(
            prompt=prompt,
            system_instruction=_COMMUNICATION_EVAL_SYSTEM_INSTRUCTION,
            response_schema=CommunicationEvaluation,
        )

    async def _call(
        self, *, prompt: str, system_instruction: str, response_schema: type[_SchemaT]
    ) -> _SchemaT:
        for attempt in (1, 2):
            try:
                response = await asyncio.wait_for(
                    self._client.aio.models.generate_content(
                        model=self._model,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            system_instruction=system_instruction,
                            temperature=0.2,
                            response_mime_type="application/json",
                            response_schema=response_schema,
                        ),
                    ),
                    timeout=self._timeout_seconds,
                )
                break
            except TimeoutError as exc:
                logger.warning(
                    "interview_intelligence.gemini.timeout", timeout_seconds=self._timeout_seconds
                )
                raise InterviewIntelligenceTimeoutError(
                    f"Gemini call timed out after {self._timeout_seconds}s"
                ) from exc
            except ServerError as exc:
                logger.warning("interview_intelligence.gemini.server_error", attempt=attempt)
                if attempt == 2:
                    raise InterviewIntelligenceProviderError(
                        f"Gemini server error after retry: {exc}"
                    ) from exc
                continue
            except ClientError as exc:
                logger.warning("interview_intelligence.gemini.client_error")
                raise InterviewIntelligenceProviderError(f"Gemini request rejected: {exc}") from exc
            except Exception as exc:  # noqa: BLE001 — any other SDK/network failure
                logger.warning("interview_intelligence.gemini.unexpected_error", error=str(exc))
                raise InterviewIntelligenceProviderError(f"Gemini request failed: {exc}") from exc

        return self._parse_response(response, response_schema)

    @staticmethod
    def _parse_response(
        response: types.GenerateContentResponse, response_schema: type[_SchemaT]
    ) -> _SchemaT:
        # google-genai populates `.parsed` with a validated instance when it
        # can — used first, but never trusted unconditionally (same
        # defensive shape as ResumeIntelligenceProvider._parse_response).
        parsed = getattr(response, "parsed", None)
        if parsed is not None:
            try:
                return response_schema.model_validate(parsed)
            except ValidationError:
                pass  # fall through to raw-text parsing below

        raw_text = getattr(response, "text", None)
        if not raw_text:
            raise InterviewIntelligenceProviderError("Gemini returned an empty response")
        try:
            data = json.loads(raw_text)
            return response_schema.model_validate(data)
        except (json.JSONDecodeError, ValidationError) as exc:
            raise InterviewIntelligenceProviderError(
                f"Gemini response failed schema validation: {exc}"
            ) from exc
