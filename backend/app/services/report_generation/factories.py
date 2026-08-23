"""Config-driven factory for ReportGenerationProvider — mirrors
app/services/code_evaluation/factories.py exactly.
"""

from app.core.config import Settings
from app.services.report_generation.fake_provider import get_fake_report_generation_provider
from app.services.report_generation.gemini_provider import GeminiReportGenerationProvider
from app.services.report_generation.provider import ReportGenerationProvider


def _reject_fake_in_production(settings: Settings, *, what: str) -> None:
    if settings.ENVIRONMENT == "production":
        raise RuntimeError(
            f"fake {what} must not be used in production; "
            f"configure a real provider before deploying"
        )


def build_report_generation_provider(settings: Settings) -> ReportGenerationProvider:
    if settings.REPORT_GENERATION_PROVIDER == "gemini":
        return GeminiReportGenerationProvider(settings)
    if settings.REPORT_GENERATION_PROVIDER == "fake":
        _reject_fake_in_production(settings, what="ReportGenerationProvider")
        return get_fake_report_generation_provider()
    raise NotImplementedError(
        f"report generation provider {settings.REPORT_GENERATION_PROVIDER!r} not wired yet"
    )
