"""InterviewAgentProvider Protocol — Module 5. Same shape as
ResumeIntelligenceProvider (app/services/resume_intelligence/provider.py):
a Protocol the graph nodes depend on, a config-selected concrete
implementation, dependency-injected via
app/services/interview_intelligence/factories.py.

One Protocol, four operations, rather than four separate Protocols — one
provider instance (one Gemini client) backs all four in practice, and
every graph node calls exactly the one method its responsibility needs
(module §2: "every agent must have a clear responsibility and typed
input/output contract" — the contract is the method signature + the
schemas.py return type, not a separate class per agent at this layer).

Deliberately takes only primitives (str/list[str]), never ORM rows or
Module 4's InterviewExecutionContext/PersonalizationContext types — mirrors
ResumeIntelligenceProvider.extract()'s own (resume_text, sections) shape.
Keeps this package fully independent of the interview-execution domain;
callers are responsible for flattening whatever context they have into
these primitives.
"""

from typing import Protocol

from app.services.interview_intelligence.schemas import (
    CommunicationEvaluation,
    GeneratedQuestion,
    TechnicalEvaluation,
)


class InterviewIntelligenceError(Exception):
    """Base for every failure mode a provider can raise. Callers catch this
    (never a raw provider-SDK exception) so swapping providers never
    changes calling code's error handling.
    """


class InterviewIntelligenceTimeoutError(InterviewIntelligenceError):
    pass


class InterviewIntelligenceProviderError(InterviewIntelligenceError):
    """Provider reachable but failed: API error, malformed/unparseable
    response, or a response that fails schema validation. Never returns a
    partially-validated or best-guess object — the caller decides what
    "the LLM failed" means for interview state (module §22), this seam
    doesn't.
    """


class InterviewAgentProvider(Protocol):
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
        """A fresh, round-opening question (Question Generator Agent,
        module §7) — never a follow-up. `asked_questions` is this
        session's already-asked question texts, for basic duplicate
        avoidance (module §17); `evidence_snippets`/`skills` are the only
        resume grounding provided — never raw resume text.
        """
        ...

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
        """A follow-up to the specific answer just given (Interview Agent,
        module §8), grounded in `follow_up_reason` (from
        TechnicalEvaluation.follow_up_reason) — never a generic "tell me
        more."
        """
        ...

    async def evaluate_technical(
        self,
        *,
        question_text: str,
        answer_text: str,
        round_type: str,
        difficulty: str,
        knowledge_context: str,
    ) -> TechnicalEvaluation:
        """Evaluation Agent (module §9) — technical + problem_solving only."""
        ...

    async def evaluate_communication(
        self, *, question_text: str, answer_text: str
    ) -> CommunicationEvaluation:
        """Communication Agent (module §11) — independent of technical
        correctness, deliberately given no evaluation/difficulty context.
        """
        ...
