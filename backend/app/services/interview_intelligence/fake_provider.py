"""FakeInterviewAgentProvider — deterministic, rule-based, no network call.
Mirrors app/services/resume_intelligence/fake_provider.py's shape exactly:
wired only via `app.dependency_overrides` in tests, never selectable
through Settings in production (see INTERVIEW_ENGINE_PROVIDER's docstring
and factories.py's `_reject_fake_in_production` guard) — a misconfigured
deployment can never end up fabricating interview evaluations through this
path.

Deliberately simple length/keyword-based heuristics rather than trying to
mimic Gemini's judgment — its job is to prove the graph/service's
persistence, idempotency, difficulty-adaptation, and error-handling logic
against schema-valid responses, and to let tests deterministically force a
specific score/outcome (`forced_*` fields) or a specific failure mode
(`fail`/`timeout`/`malformed`) without touching real infrastructure. This
is also the reason the earlier Gemini structured-output bug (see
app/services/resume_intelligence/schemas.py) went uncaught for so long —
a fake provider that never goes through the real SDK's schema conversion
structurally cannot catch that class of bug. See
tests/test_resume_intelligence_gemini_schema.py's regression tests for how
that's covered instead; the same reasoning applies here (no live-SDK
schema-conversion test exists yet for this provider's schemas because no
such bug has been found in them — see this module's docstring rule
inherited from schemas.py).
"""

import re

from app.services.interview_intelligence.provider import (
    InterviewIntelligenceProviderError,
    InterviewIntelligenceTimeoutError,
)
from app.services.interview_intelligence.schemas import (
    CommunicationEvaluation,
    GeneratedQuestion,
    TechnicalEvaluation,
)


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def _heuristic_score(answer_text: str) -> float:
    """Deterministic: more (space-separated) words -> a higher score, capped.
    Just enough variation for tests to exercise "weak vs strong answer"
    without hand-crafting text for every case; tests wanting an exact score
    should set `forced_*` instead.
    """
    word_count = len(answer_text.split())
    return float(min(95, 30 + word_count * 4))


class FakeInterviewAgentProvider:
    def __init__(
        self, *, fail: bool = False, timeout: bool = False, malformed: bool = False
    ) -> None:
        self.fail = fail
        self.timeout = timeout
        self.malformed = malformed
        # Tests set these to pin an exact score/outcome for a specific
        # answer (e.g. to deterministically trigger a difficulty
        # increase/decrease) instead of relying on the length heuristic.
        self.forced_technical_score: float | None = None
        self.forced_problem_solving_score: float | None = None
        self.forced_communication_score: float | None = None
        self.forced_confidence_score: float | None = None
        self.forced_follow_up_worthy: bool | None = None
        self.calls: list[str] = []

    def reset(self) -> None:
        self.fail = False
        self.timeout = False
        self.malformed = False
        self.forced_technical_score = None
        self.forced_problem_solving_score = None
        self.forced_communication_score = None
        self.forced_confidence_score = None
        self.forced_follow_up_worthy = None
        self.calls = []

    def _maybe_fail(self, call_name: str) -> None:
        if self.timeout:
            raise InterviewIntelligenceTimeoutError(
                f"fake provider: simulated timeout ({call_name})"
            )
        if self.fail:
            raise InterviewIntelligenceProviderError(
                f"fake provider: simulated provider failure ({call_name})"
            )
        if self.malformed:
            # Exercises the caller's defensive-parsing path: a provider
            # that raises this exact error is indistinguishable from one
            # whose JSON failed pydantic validation upstream.
            raise InterviewIntelligenceProviderError(
                f"fake provider: simulated malformed/unparseable response ({call_name})"
            )

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
        self.calls.append("generate_question")
        self._maybe_fail("generate_question")

        topic = skills[0] if skills else f"{round_type} fundamentals"
        base_text = f"[{difficulty}] Tell me about {topic} in the context of the {role_title} role."
        text = base_text
        already_asked = {_normalize(q) for q in asked_questions}
        variant = 2
        while _normalize(text) in already_asked:
            text = f"{base_text} (variant {variant})"
            variant += 1

        return GeneratedQuestion(question_text=text, topic=topic, grounded_in_resume=bool(skills))

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
        self.calls.append("generate_follow_up")
        self._maybe_fail("generate_follow_up")

        return GeneratedQuestion(
            question_text=f"Can you go deeper on this: {follow_up_reason}?",
            topic="follow_up",
            grounded_in_resume=False,
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
        self.calls.append("evaluate_technical")
        self._maybe_fail("evaluate_technical")

        score = (
            self.forced_technical_score
            if self.forced_technical_score is not None
            else _heuristic_score(answer_text)
        )
        problem_solving_score = (
            self.forced_problem_solving_score
            if self.forced_problem_solving_score is not None
            else score
        )
        follow_up_worthy = (
            self.forced_follow_up_worthy if self.forced_follow_up_worthy is not None else score < 50
        )
        return TechnicalEvaluation(
            technical_score=score,
            technical_explanation=f"Fake evaluation from answer length ({len(answer_text)} chars).",
            problem_solving_score=problem_solving_score,
            problem_solving_explanation="Fake problem-solving evaluation.",
            missing_concepts=[] if score >= 70 else ["deeper edge-case handling"],
            strengths=["clear structure"] if score >= 70 else [],
            weaknesses=[] if score >= 70 else ["shallow explanation"],
            follow_up_worthy=follow_up_worthy,
            follow_up_reason=(
                "the answer looks shallow — worth probing" if follow_up_worthy else None
            ),
        )

    async def evaluate_communication(
        self, *, question_text: str, answer_text: str
    ) -> CommunicationEvaluation:
        self.calls.append("evaluate_communication")
        self._maybe_fail("evaluate_communication")

        score = (
            self.forced_communication_score
            if self.forced_communication_score is not None
            else _heuristic_score(answer_text)
        )
        confidence = (
            self.forced_confidence_score if self.forced_confidence_score is not None else score
        )
        return CommunicationEvaluation(
            communication_score=score,
            communication_explanation="Fake communication evaluation.",
            confidence_score=confidence,
            confidence_explanation="Fake phrasing-directness evaluation.",
        )


# Module-level singleton: some Module 5 code paths (background/graph node
# execution) may not always have a clean FastAPI request/DI context by the
# time they run — same rationale as
# app/services/resume_intelligence/fake_provider.py. Tests mutate this
# singleton's fields directly (see tests/conftest.py's autouse reset
# fixture) instead of constructing a new instance per test.
_singleton = FakeInterviewAgentProvider()


def get_fake_interview_agent_provider() -> FakeInterviewAgentProvider:
    return _singleton
