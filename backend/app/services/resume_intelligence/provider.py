"""ResumeIntelligenceProvider Protocol — module §8. Same shape as
CodeExecutor/JobRunner: a Protocol the domain depends on, a
config-selected concrete implementation, dependency-injected via
app/api/deps.py.
"""

from typing import Protocol

from app.services.resume_intelligence.schemas import ExtractedProfile


class ResumeIntelligenceError(Exception):
    """Base for every failure mode a provider can raise. ResumeService
    catches this (not raw provider-SDK exceptions) so swapping providers
    never changes ResumeService's error handling.
    """


class ResumeIntelligenceTimeoutError(ResumeIntelligenceError):
    pass


class ResumeIntelligenceProviderError(ResumeIntelligenceError):
    """Provider reachable but failed: API error, malformed/unparseable
    response, or a response that fails ExtractedProfile validation.
    """


class ResumeIntelligenceProvider(Protocol):
    async def extract(self, *, resume_text: str, sections: dict[str, str]) -> ExtractedProfile:
        """Returns a validated ExtractedProfile or raises
        ResumeIntelligenceTimeoutError / ResumeIntelligenceProviderError.
        Never returns a partially-validated or best-guess object — the
        caller's job (ResumeService) is to decide what "partial success"
        means at the persistence layer, not this seam.
        """
        ...
