"""ChromaDB connection wrapper.

Connection setup only — collection schemas (`question_bank`, `knowledge_base`,
`resume_embeddings` per Database.md §9) and embedding logic are not created
here. Those land with Module 3 (Resume Intelligence) and Module 5 (Knowledge
Agent), which are the first features that actually read/write vectors.
"""

from functools import lru_cache

import chromadb

from app.core.config import get_settings


@lru_cache
def get_chroma_client() -> chromadb.ClientAPI:
    settings = get_settings()
    return chromadb.HttpClient(host=settings.CHROMA_HOST, port=settings.CHROMA_PORT)
