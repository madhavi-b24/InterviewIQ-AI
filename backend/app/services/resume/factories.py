"""Config-driven factories for Resume Intelligence's pluggable seams
(ResumeStorage, ResumeIntelligenceProvider, EmbeddingProvider/ChromaDB) —
plain functions, not FastAPI `Depends`, so both app/api/deps.py (request
handlers) and app/jobs/resume_processing.py (the background job, which
has no request/DI context) build the exact same objects the exact same
way. Mirrors app/api/deps.py's get_job_runner/get_code_executor pattern.
"""

from app.core.config import Settings
from app.services.resume_intelligence.embedding_provider import (
    EmbeddingProvider,
    GeminiEmbeddingProvider,
)
from app.services.resume_intelligence.fake_embedding_provider import get_fake_embedding_provider
from app.services.resume_intelligence.fake_provider import get_fake_resume_intelligence_provider
from app.services.resume_intelligence.gemini_provider import GeminiResumeIntelligenceProvider
from app.services.resume_intelligence.provider import ResumeIntelligenceProvider
from app.storage.base import ResumeStorage
from app.storage.local import LocalResumeStorage
from app.vectorstore.client import get_chroma_client
from app.vectorstore.resume_embeddings import ResumeEmbeddingIndex


def _reject_fake_in_production(settings: Settings, *, what: str) -> None:
    if settings.ENVIRONMENT == "production":
        raise RuntimeError(
            f"fake {what} must not be used in production; "
            f"configure a real provider before deploying"
        )


def build_resume_storage(settings: Settings) -> ResumeStorage:
    if settings.RESUME_STORAGE_BACKEND == "local":
        return LocalResumeStorage(settings)
    raise NotImplementedError(
        f"resume storage backend {settings.RESUME_STORAGE_BACKEND!r} not wired yet"
    )


def build_resume_intelligence_provider(settings: Settings) -> ResumeIntelligenceProvider:
    if settings.RESUME_INTELLIGENCE_PROVIDER == "gemini":
        return GeminiResumeIntelligenceProvider(settings)
    if settings.RESUME_INTELLIGENCE_PROVIDER == "fake":
        _reject_fake_in_production(settings, what="ResumeIntelligenceProvider")
        return get_fake_resume_intelligence_provider()
    raise NotImplementedError(
        f"resume intelligence provider {settings.RESUME_INTELLIGENCE_PROVIDER!r} not wired yet"
    )


def build_embedding_provider(settings: Settings) -> EmbeddingProvider:
    if settings.RESUME_EMBEDDING_PROVIDER == "gemini":
        return GeminiEmbeddingProvider(settings)
    if settings.RESUME_EMBEDDING_PROVIDER == "fake":
        _reject_fake_in_production(settings, what="EmbeddingProvider")
        return get_fake_embedding_provider()
    raise NotImplementedError(
        f"embedding provider {settings.RESUME_EMBEDDING_PROVIDER!r} not wired yet"
    )


def build_embedding_index(settings: Settings) -> ResumeEmbeddingIndex:
    return ResumeEmbeddingIndex(get_chroma_client(), build_embedding_provider(settings))
