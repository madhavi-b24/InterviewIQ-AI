"""Config-driven factory for CodeEvaluationProvider — mirrors
app/services/interview_intelligence/factories.py exactly.
"""

from app.core.config import Settings
from app.services.code_evaluation.fake_provider import get_fake_code_evaluation_provider
from app.services.code_evaluation.gemini_provider import GeminiCodeEvaluationProvider
from app.services.code_evaluation.provider import CodeEvaluationProvider


def _reject_fake_in_production(settings: Settings, *, what: str) -> None:
    if settings.ENVIRONMENT == "production":
        raise RuntimeError(
            f"fake {what} must not be used in production; "
            f"configure a real provider before deploying"
        )


def build_code_evaluation_provider(settings: Settings) -> CodeEvaluationProvider:
    if settings.CODE_EVALUATION_PROVIDER == "gemini":
        return GeminiCodeEvaluationProvider(settings)
    if settings.CODE_EVALUATION_PROVIDER == "fake":
        _reject_fake_in_production(settings, what="CodeEvaluationProvider")
        return get_fake_code_evaluation_provider()
    raise NotImplementedError(
        f"code evaluation provider {settings.CODE_EVALUATION_PROVIDER!r} not wired yet"
    )
