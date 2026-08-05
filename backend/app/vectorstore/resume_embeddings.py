"""resume_embeddings collection (Database.md §9, module §14) — indexes
resume evidence chunks (skill/project/experience/certification evidence
text) for future semantic retrieval by the Interview Engine's Question
Generator/Knowledge Agent (not built yet — this only prepares the boundary).

Design:
  - every vector is embedded via EmbeddingProvider *before* it reaches
    Chroma (see embedding_provider.py's docstring for why)
  - every id/metadata row carries both user_id and resume_id, so a
    consumer can (and, per module §15, MUST) filter by user_id — this
    module itself never returns cross-user results because `query`
    requires a user_id
  - idempotent: `reindex_resume` deletes this resume's existing vectors
    before adding fresh ones, so re-processing a resume (or a shrinking
    edit) never leaves stale chunks behind
  - `delete_resume` supports removal when a Resume row is deleted

Not queried by anything yet in this module — GET /resumes/{id}/analysis
reads structured Postgres rows, not Chroma. This only builds the
indexing boundary the future Knowledge Agent will read from.
"""

import asyncio
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from app.core.logging import get_logger
from app.services.resume_intelligence.embedding_provider import EmbeddingProvider

logger = get_logger(__name__)

RESUME_EMBEDDINGS_COLLECTION = "resume_embeddings"


@dataclass(frozen=True, slots=True)
class EvidenceChunk:
    chunk_id: str  # stable within a resume, e.g. "skill:3", "project:0"
    kind: str  # "skill" | "project" | "experience" | "certification" | "summary"
    name: str  # display label — skill name / project title / company name
    text: str  # the evidence text actually embedded


class ChromaCollectionLike(Protocol):
    """The minimal chromadb Collection surface this module uses — narrow
    enough that tests can satisfy it with an in-memory fake instead of a
    live ChromaDB server (see tests/fake_chroma.py).
    """

    def upsert(self, *, ids, embeddings, documents, metadatas) -> None: ...
    def delete(self, *, where) -> None: ...
    def query(self, *, query_embeddings, n_results, where): ...


class ChromaClientLike(Protocol):
    def get_or_create_collection(self, name: str) -> ChromaCollectionLike: ...


class ResumeEmbeddingIndex:
    def __init__(
        self, chroma_client: ChromaClientLike, embedding_provider: EmbeddingProvider
    ) -> None:
        self._client = chroma_client
        self._embeddings = embedding_provider

    async def reindex_resume(
        self, *, user_id: UUID, resume_id: UUID, chunks: list[EvidenceChunk]
    ) -> None:
        await asyncio.to_thread(self._delete_sync, resume_id)
        if not chunks:
            return

        texts = [chunk.text for chunk in chunks]
        vectors = await self._embeddings.embed(texts)
        ids = [f"{resume_id}:{chunk.chunk_id}" for chunk in chunks]
        metadatas = [
            {
                "user_id": str(user_id),
                "resume_id": str(resume_id),
                "kind": chunk.kind,
                "name": chunk.name,
            }
            for chunk in chunks
        ]
        await asyncio.to_thread(self._upsert_sync, ids, vectors, texts, metadatas)
        logger.info("resume_embeddings.indexed", resume_id=str(resume_id), chunk_count=len(chunks))

    async def delete_resume(self, resume_id: UUID) -> None:
        await asyncio.to_thread(self._delete_sync, resume_id)

    async def query(
        self, *, user_id: UUID, query_text: str, resume_id: UUID | None = None, top_k: int = 5
    ):
        """Scoped strictly to `user_id` (and optionally one `resume_id`) —
        the only entry point a future caller has into this collection, so
        cross-user retrieval is structurally impossible through this class.
        """
        vectors = await self._embeddings.embed([query_text])
        where = {"user_id": str(user_id)}
        if resume_id is not None:
            where = {"$and": [where, {"resume_id": str(resume_id)}]}
        return await asyncio.to_thread(self._query_sync, vectors[0], where, top_k)

    def _collection(self) -> ChromaCollectionLike:
        return self._client.get_or_create_collection(RESUME_EMBEDDINGS_COLLECTION)

    def _delete_sync(self, resume_id: UUID) -> None:
        self._collection().delete(where={"resume_id": str(resume_id)})

    def _upsert_sync(
        self, ids: list[str], vectors: list[list[float]], texts: list[str], metadatas: list[dict]
    ) -> None:
        self._collection().upsert(ids=ids, embeddings=vectors, documents=texts, metadatas=metadatas)

    def _query_sync(self, vector: list[float], where: dict, top_k: int):
        return self._collection().query(query_embeddings=[vector], n_results=top_k, where=where)


def build_evidence_chunks_from_profile(
    *,
    skills: list[tuple[str, str | None]],
    projects: list[tuple[str, str | None]],
    experience: list[tuple[str, str | None]],
    certifications: list[tuple[str, str | None]],
) -> list[EvidenceChunk]:
    """Assembles the chunk list from (name, evidence_text) pairs already
    persisted by ResumeService — kept as a free function so the caller
    doesn't need to import EvidenceChunk's field order.
    """
    chunks: list[EvidenceChunk] = []
    for index, (name, evidence) in enumerate(skills):
        if evidence:
            chunks.append(EvidenceChunk(f"skill:{index}", "skill", name, evidence))
    for index, (name, evidence) in enumerate(projects):
        if evidence:
            chunks.append(EvidenceChunk(f"project:{index}", "project", name, evidence))
    for index, (name, evidence) in enumerate(experience):
        if evidence:
            chunks.append(EvidenceChunk(f"experience:{index}", "experience", name, evidence))
    for index, (name, evidence) in enumerate(certifications):
        if evidence:
            chunks.append(EvidenceChunk(f"certification:{index}", "certification", name, evidence))
    return chunks
