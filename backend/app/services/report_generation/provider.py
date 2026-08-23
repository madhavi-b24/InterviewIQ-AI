"""ReportGenerationProvider Protocol — Module 7. Same shape as
CodeEvaluationProvider/InterviewAgentProvider: a Protocol the calling
service depends on, a config-selected concrete implementation,
dependency-injected via app/services/report_generation/factories.py.

Deliberately takes only primitives, never ORM rows — keeps this package
fully independent of the report/interview domain, mirroring every other
provider's independence.
"""

from dataclasses import dataclass
from typing import Protocol

from app.services.report_generation.schemas import ReportContentResult


@dataclass(frozen=True, slots=True)
class AnswerEvidence:
    """One evaluation dimension's already-computed score + explanation,
    handed to the provider as grounding material for the narrative it
    writes — never the raw answer/source text, and never re-judged by
    this provider (module §20: no chain-of-thought, no re-litigating an
    answer already scored by Module 5/6's evaluators; this provider only
    synthesizes explanations that already exist into a session-level
    narrative).
    """

    round_type: str
    dimension: str  # "technical" | "problem_solving" | "communication" | "confidence" | "coding"
    score: float
    explanation: str


class ReportGenerationError(Exception):
    """Base for every failure mode a provider can raise. Callers catch this
    (never a raw provider-SDK exception) so swapping providers never
    changes calling code's error handling.
    """


class ReportGenerationTimeoutError(ReportGenerationError):
    pass


class ReportGenerationProviderError(ReportGenerationError):
    """Provider reachable but failed: API error, malformed/unparseable
    response, or a response that fails schema validation. Never returns a
    partially-validated or best-guess object.
    """


class ReportGenerationProvider(Protocol):
    async def generate(
        self,
        *,
        role_title: str,
        company_name: str | None,
        section_scores: dict[str, float],
        overall_score: float,
        evidence: list[AnswerEvidence],
    ) -> ReportContentResult:
        """Writes the narrative half of a session report — every score
        given here (`section_scores`, `overall_score`, and each
        `AnswerEvidence.score`) is already final, computed deterministically
        by app/agents/policy.py before this call; this provider is never
        asked to compute or revise a score, only to explain what the
        numbers mean and identify weak/strong topics + roadmap resources
        from the evidence it's given.
        """
        ...
