"""FakeCodeEvaluationProvider — deterministic, no network call. Mirrors
app/services/interview_intelligence/fake_provider.py's shape exactly:
`fail`/`timeout` flags, `forced_*` overrides, `.reset()`, `.calls` log,
module-level singleton — wired only via `app.dependency_overrides` in
tests, never selectable through Settings in production (factories.py's
`_reject_fake_in_production` guard).
"""

from app.services.code_evaluation.provider import (
    CodeEvaluationProviderError,
    CodeEvaluationTimeoutError,
)
from app.services.code_evaluation.schemas import CodeEvaluationResult


class FakeCodeEvaluationProvider:
    def __init__(self, *, fail: bool = False, timeout: bool = False) -> None:
        self.fail = fail
        self.timeout = timeout
        self.forced_readability_score: float | None = None
        self.forced_optimization_score: float | None = None
        self.forced_edge_case_score: float | None = None
        self.calls: list[str] = []

    def reset(self) -> None:
        self.fail = False
        self.timeout = False
        self.forced_readability_score = None
        self.forced_optimization_score = None
        self.forced_edge_case_score = None
        self.calls = []

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
        self.calls.append("evaluate")
        if self.timeout:
            raise CodeEvaluationTimeoutError("fake provider: simulated timeout")
        if self.fail:
            raise CodeEvaluationProviderError("fake provider: simulated provider failure")

        readability = (
            self.forced_readability_score if self.forced_readability_score is not None else 80.0
        )
        optimization = (
            self.forced_optimization_score if self.forced_optimization_score is not None else 70.0
        )
        edge_case = self.forced_edge_case_score if self.forced_edge_case_score is not None else 75.0
        return CodeEvaluationResult(
            readability_score=readability,
            readability_explanation=f"Fake readability evaluation ({len(source_code)} chars).",
            optimization_score=optimization,
            optimization_explanation="Fake optimization evaluation.",
            edge_case_score=edge_case,
            edge_case_explanation="Fake edge-case evaluation.",
            time_complexity="O(n)",
            space_complexity="O(1)",
            strengths=["clear structure"] if readability >= 70 else [],
            weaknesses=[] if readability >= 70 else ["hard to follow"],
            recommendations=["add a docstring"],
        )


_singleton = FakeCodeEvaluationProvider()


def get_fake_code_evaluation_provider() -> FakeCodeEvaluationProvider:
    return _singleton
