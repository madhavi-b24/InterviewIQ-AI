"""Config-driven factory for the Interview Engine's pluggable LLM seam —
plain function, not a FastAPI `Depends`, mirroring
app/services/resume/factories.py's `build_resume_intelligence_provider`
exactly (same production guard, same shape) so any future non-request
caller (e.g. a background job) can build the identical object the exact
same way app/api/deps.py does.
"""

from app.core.config import Settings
from app.services.interview_intelligence.fake_provider import get_fake_interview_agent_provider
from app.services.interview_intelligence.gemini_provider import GeminiInterviewAgentProvider
from app.services.interview_intelligence.provider import InterviewAgentProvider


def _reject_fake_in_production(settings: Settings, *, what: str) -> None:
    if settings.ENVIRONMENT == "production":
        raise RuntimeError(
            f"fake {what} must not be used in production; "
            f"configure a real provider before deploying"
        )


def build_interview_agent_provider(settings: Settings) -> InterviewAgentProvider:
    if settings.INTERVIEW_ENGINE_PROVIDER == "gemini":
        return GeminiInterviewAgentProvider(settings)
    if settings.INTERVIEW_ENGINE_PROVIDER == "fake":
        _reject_fake_in_production(settings, what="InterviewAgentProvider")
        return get_fake_interview_agent_provider()
    raise NotImplementedError(
        f"interview engine provider {settings.INTERVIEW_ENGINE_PROVIDER!r} not wired yet"
    )
