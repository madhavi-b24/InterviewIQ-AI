"""ResumeStorage abstraction — module-3 equivalent of app/execution/base.py
and app/jobs/base.py: a Protocol + config-selected implementation
(RESUME_STORAGE_BACKEND), so the Resume Intelligence domain never depends
on "where bytes live" directly.

`LocalResumeStorage` (app/storage/local.py) is the MVP backend. Swapping
in an object-storage backend (Azure Blob/S3) later means writing one new
class against this Protocol and flipping RESUME_STORAGE_BACKEND — no
change to ResumeService or the background job that calls it.
"""

from typing import Protocol


class ResumeStorage(Protocol):
    async def save(self, *, storage_key: str, content: bytes) -> str:
        """Persist `content` under `storage_key` (server-generated — see
        ResumeService, never a client-supplied filename). Returns the
        value to persist in resumes.file_url: a logical locator the same
        backend can resolve later, never an absolute filesystem path or
        anything otherwise meaningful to expose to a client.
        """
        ...

    async def read(self, *, storage_key: str) -> bytes:
        """Raise FileNotFoundError if storage_key does not exist."""
        ...

    async def delete(self, *, storage_key: str) -> None:
        """Best-effort delete. Must not raise if storage_key is already gone."""
        ...
