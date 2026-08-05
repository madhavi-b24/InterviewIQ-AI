"""EmbeddingProvider — precomputed vectors for ChromaDB (module §14).

We depend on `chromadb-client` (the thin HTTP client — see
app/vectorstore/client.py's docstring), which has no local embedding
function available (that requires the full `chromadb` package's
onnxruntime/hnswlib stack, deliberately avoided). So every vector written
to Chroma is computed here first and passed to the collection explicitly
— this Protocol is that seam, mirroring ResumeIntelligenceProvider.
"""

import asyncio
from typing import Protocol

from google import genai
from google.genai import types

from app.core.config import Settings


class EmbeddingProviderError(Exception):
    pass


class EmbeddingProvider(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Returns one embedding vector per input text, same order,
        same length as `texts`. Raises EmbeddingProviderError on failure.
        """
        ...


class GeminiEmbeddingProvider:
    def __init__(self, settings: Settings) -> None:
        if not settings.GEMINI_API_KEY:
            raise EmbeddingProviderError("GEMINI_API_KEY is not configured")
        self._client = genai.Client(api_key=settings.GEMINI_API_KEY)
        self._model = settings.GEMINI_EMBEDDING_MODEL

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        try:
            response = await asyncio.wait_for(
                self._client.aio.models.embed_content(
                    model=self._model,
                    contents=texts,
                    config=types.EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT"),
                ),
                timeout=30,
            )
        except Exception as exc:  # noqa: BLE001 — any SDK/network failure becomes a domain error
            raise EmbeddingProviderError(f"Gemini embedding request failed: {exc}") from exc

        embeddings = response.embeddings or []
        if len(embeddings) != len(texts):
            raise EmbeddingProviderError(
                f"Gemini returned {len(embeddings)} embeddings for {len(texts)} inputs"
            )
        return [list(item.values or []) for item in embeddings]
