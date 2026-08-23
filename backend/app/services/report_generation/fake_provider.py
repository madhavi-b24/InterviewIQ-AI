"""FakeReportGenerationProvider — deterministic, no network call. Mirrors
app/services/code_evaluation/fake_provider.py's shape exactly: `fail`/
`timeout` flags, `.reset()`, `.calls` log, module-level singleton — wired
only via `app.dependency_overrides` in request-handler tests, and via
direct singleton mutation in tests that exercise the background job
(the job builds its own provider instance outside FastAPI's DI, same
reasoning as FakeCodeEvaluationProvider's docstring), never selectable
through Settings in production (factories.py's `_reject_fake_in_production`
guard).
"""

from app.services.report_generation.provider import (
    AnswerEvidence,
    ReportGenerationProviderError,
    ReportGenerationTimeoutError,
)
from app.services.report_generation.schemas import (
    ReportContentResult,
    RoadmapItemContent,
    StrongAreaContent,
    WeakAreaContent,
)


class FakeReportGenerationProvider:
    def __init__(self, *, fail: bool = False, timeout: bool = False) -> None:
        self.fail = fail
        self.timeout = timeout
        self.calls: list[str] = []

    def reset(self) -> None:
        self.fail = False
        self.timeout = False
        self.calls = []

    async def generate(
        self,
        *,
        role_title: str,
        company_name: str | None,
        section_scores: dict[str, float],
        overall_score: float,
        evidence: list[AnswerEvidence],
    ) -> ReportContentResult:
        self.calls.append("generate")
        if self.timeout:
            raise ReportGenerationTimeoutError("fake provider: simulated timeout")
        if self.fail:
            raise ReportGenerationProviderError("fake provider: simulated provider failure")

        weak_areas = [
            WeakAreaContent(
                topic=name.replace("_", " ").title(),
                section=name,
                evidence_text=f"Fake evidence for {name}.",
            )
            for name, score in section_scores.items()
            if score < 65.0
        ]
        strong_areas = [
            StrongAreaContent(
                topic=name.replace("_", " ").title(),
                section=name,
                evidence_text=f"Fake evidence for {name}.",
            )
            for name, score in section_scores.items()
            if score >= 80.0
        ]
        roadmap_items = [
            RoadmapItemContent(
                topic=area.topic,
                resource_title=f"Fake resource for {area.topic}",
                resource_url="https://example.com/fake-resource",
                resource_type="article",
                priority=i + 1,
            )
            for i, area in enumerate(weak_areas)
        ]
        coding_explanation = "Fake coding explanation." if "coding" in section_scores else None
        summary_suffix = f" at {company_name}." if company_name else "."
        return ReportContentResult(
            technical_explanation="Fake technical explanation.",
            problem_solving_explanation="Fake problem-solving explanation.",
            communication_explanation="Fake communication explanation.",
            confidence_explanation="Fake confidence explanation.",
            coding_explanation=coding_explanation,
            overall_explanation=f"Fake overall explanation (score={overall_score}).",
            summary_text=f"Fake summary for {role_title}" + summary_suffix,
            weak_areas=weak_areas,
            strong_areas=strong_areas,
            roadmap_items=roadmap_items,
        )


_singleton = FakeReportGenerationProvider()


def get_fake_report_generation_provider() -> FakeReportGenerationProvider:
    return _singleton
