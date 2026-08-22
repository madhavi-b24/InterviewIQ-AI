"""CodeEvaluationProvider Protocol — Module 6. Same shape as
InterviewAgentProvider/ResumeIntelligenceProvider: a Protocol the calling
service depends on, a config-selected concrete implementation,
dependency-injected via app/services/code_evaluation/factories.py.

Deliberately takes only primitives, never ORM rows or the CodeExecutor's
own dataclasses — keeps this package fully independent of the coding
-round execution domain, mirroring every other provider's independence.
"""

from typing import Protocol

from app.services.code_evaluation.schemas import CodeEvaluationResult


class CodeEvaluationError(Exception):
    """Base for every failure mode a provider can raise. Callers catch this
    (never a raw provider-SDK exception) so swapping providers never
    changes calling code's error handling.
    """


class CodeEvaluationTimeoutError(CodeEvaluationError):
    pass


class CodeEvaluationProviderError(CodeEvaluationError):
    """Provider reachable but failed: API error, malformed/unparseable
    response, or a response that fails schema validation. Never returns a
    partially-validated or best-guess object.
    """


class CodeEvaluationProvider(Protocol):
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
        """Judges qualities test execution can't measure for a *final*
        submission only — never asked to (and never able to) decide
        correctness; `passed_test_count`/`total_test_count` are given only
        as grounding context for the narrative explanations, not something
        this call computes or can override.
        """
        ...
