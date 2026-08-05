"""FakeEmbeddingProvider — deterministic, hash-derived fixed-dimension
vectors. No network call. Wired only via app.dependency_overrides in
tests, same rationale as fake_provider.py.
"""

import hashlib

_DIMENSIONS = 32


class FakeEmbeddingProvider:
    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vector_for(text) for text in texts]

    @staticmethod
    def _vector_for(text: str) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        # Repeat the digest to fill _DIMENSIONS bytes, map each byte to [-1, 1].
        raw = (digest * (_DIMENSIONS // len(digest) + 1))[:_DIMENSIONS]
        return [(byte / 127.5) - 1.0 for byte in raw]


# Same rationale as fake_provider.py's singleton — the background job
# builds this via app/services/resume/factories.py, outside FastAPI's DI.
_singleton = FakeEmbeddingProvider()


def get_fake_embedding_provider() -> FakeEmbeddingProvider:
    return _singleton
