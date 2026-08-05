"""ResumeService — the use-case layer for Resume Intelligence (module §2,
§10, §11, §15, §16), mirroring AuthService's shape: routers call exactly
these methods, own no SQL/storage/security logic themselves.

Every read/delete method takes `user_id` and resolves the resume through
ResumeRepository's owner-scoped queries — there is no method here that
fetches a resume by id alone. That is the ownership-enforcement
mechanism (module §15), not an afterthought layered on top.
"""

import asyncio
import hashlib
import re
import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.exceptions import ConflictError, NotFoundError, UnprocessableEntityError
from app.core.logging import get_logger
from app.models.enums import ParsedStatus
from app.models.resume import Resume, ResumeGapAnalysis
from app.models.user import User
from app.repositories.resume import ResumeRepository
from app.services.resume.pdf import validate_pdf_upload
from app.services.resume.readiness import compute_interview_level, compute_role_readiness
from app.services.resume.role_profiles import available_role_keys, get_role_profile
from app.storage.base import ResumeStorage
from app.vectorstore.resume_embeddings import ResumeEmbeddingIndex

logger = get_logger(__name__)

_ALLOWED_UPLOAD_CONTENT_TYPES = {None, "", "application/pdf", "application/octet-stream"}


class ResumeService:
    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
        storage: ResumeStorage,
        embedding_index_factory: Callable[[], ResumeEmbeddingIndex],
    ) -> None:
        self._session = session
        self._settings = settings
        self._storage = storage
        # A factory, not a resolved instance — constructing a
        # ResumeEmbeddingIndex means constructing an EmbeddingProvider,
        # which can raise (e.g. GEMINI_API_KEY unset). Only delete_resume's
        # best-effort cleanup ever needs one, so building it eagerly here
        # would make GEMINI_API_KEY required for upload/list/get too — see
        # app/api/deps.py's get_resume_service docstring.
        self._embedding_index_factory = embedding_index_factory
        self._resumes = ResumeRepository(session)

    # --- Upload ------------------------------------------------------

    async def upload(
        self,
        *,
        user: User,
        filename: str | None,
        content_type: str | None,
        content: bytes,
    ) -> Resume:
        display_name = _sanitize_filename(filename)
        _validate_extension(display_name)
        _validate_content_type(content_type)
        # pypdf parsing is CPU-bound (struct/zlib work under the hood) —
        # offloaded so it never blocks the event loop other requests share,
        # even though a resume-sized PDF alone is fast.
        await asyncio.to_thread(
            validate_pdf_upload,
            content,
            max_bytes=self._settings.RESUME_MAX_UPLOAD_MB * 1024 * 1024,
        )

        # Server-generated, never derived from the client filename — see
        # app/storage/local.py's docstring on why this matters.
        storage_key = f"{user.id}/{uuid.uuid4().hex}.pdf"
        await self._storage.save(storage_key=storage_key, content=content)

        # Versioning (module §10): the new upload becomes the sole active
        # resume; every prior upload is retained, just no longer active.
        await self._resumes.deactivate_all_for_user(user.id)

        resume = Resume(
            user_id=user.id,
            file_url=storage_key,
            original_filename=display_name,
            parsed_status=ParsedStatus.PENDING,
            is_active=True,
            mime_type="application/pdf",
            file_size_bytes=len(content),
            content_sha256=hashlib.sha256(content).hexdigest(),
        )
        await self._resumes.add(resume)
        await self._session.commit()
        logger.info("resume.uploaded", resume_id=str(resume.id), user_id=str(user.id))
        return resume

    # --- Reads ---------------------------------------------------------

    async def list_resumes(self, user_id: uuid.UUID) -> list[Resume]:
        return await self._resumes.list_by_user(user_id)

    async def get_resume(self, resume_id: uuid.UUID, user_id: uuid.UUID) -> Resume:
        resume = await self._resumes.get_owned(resume_id, user_id)
        if resume is None:
            raise NotFoundError("resume not found")
        return resume

    async def get_resume_with_analysis(self, resume_id: uuid.UUID, user_id: uuid.UUID) -> Resume:
        resume = await self._resumes.get_owned_with_children(resume_id, user_id)
        if resume is None:
            raise NotFoundError("resume not found")
        return resume

    # --- Delete ----------------------------------------------------------

    async def delete_resume(self, resume_id: uuid.UUID, user_id: uuid.UUID) -> None:
        resume = await self.get_resume(resume_id, user_id)
        was_active = resume.is_active
        storage_key = resume.file_url

        await self._session.delete(resume)
        await self._session.flush()

        if was_active:
            successor = await self._resumes.most_recent_other_resume(
                user_id, exclude_resume_id=resume_id
            )
            if successor is not None:
                successor.is_active = True

        await self._session.commit()
        logger.info("resume.deleted", resume_id=str(resume_id), user_id=str(user_id))

        # Best-effort cleanup — a storage/vector-store hiccup here must not
        # resurrect the already-deleted Postgres row or fail the request.
        try:
            await self._storage.delete(storage_key=storage_key)
        except Exception as exc:  # noqa: BLE001
            logger.warning("resume.delete.storage_cleanup_failed", error=str(exc))
        try:
            embedding_index = self._embedding_index_factory()
            await embedding_index.delete_resume(resume_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("resume.delete.embedding_cleanup_failed", error=str(exc))

    # --- Role readiness / difficulty recommendation (module §11, §12) ---

    async def generate_role_readiness(
        self, *, resume_id: uuid.UUID, user_id: uuid.UUID, role_key: str
    ) -> ResumeGapAnalysis:
        resume = await self.get_resume_with_analysis(resume_id, user_id)
        if resume.parsed_status != ParsedStatus.DONE:
            raise ConflictError(
                "resume analysis is not ready yet — wait for parsed_status=done before "
                "requesting role readiness",
                details={"parsed_status": resume.parsed_status.value},
            )

        role_profile = get_role_profile(role_key)
        if role_profile is None:
            raise NotFoundError(
                f"unknown role_key {role_key!r}",
                details={"available_role_keys": available_role_keys()},
            )

        canonical_skills = [skill.skill_name for skill in resume.skills]
        readiness = compute_role_readiness(
            canonical_skills=canonical_skills, role_profile=role_profile
        )
        project_texts = [p.evidence_text or p.description or "" for p in resume.projects]
        experience_texts = [e.evidence_text or e.description or "" for e in resume.experience]
        difficulty = compute_interview_level(
            canonical_skills=canonical_skills,
            project_texts=project_texts,
            experience_texts=experience_texts,
            role_profile=role_profile,
        )
        explanation = (
            f"Matches {len(readiness.matching_skills)}/{len(role_profile.required_skills)} "
            f"core skills for {role_profile.label}. "
            f"Missing: {', '.join(readiness.missing_skills) or 'none'}."
        )

        now = datetime.now(UTC)
        gap = resume.gap_analysis
        if gap is not None:
            gap.role_key = role_key
            gap.missing_skills = readiness.missing_skills
            gap.matching_skills = readiness.matching_skills
            gap.strengths = readiness.strengths
            gap.focus_areas = readiness.focus_areas
            gap.recommended_difficulty = difficulty.level
            gap.difficulty_reasons = difficulty.reasons
            gap.confidence = difficulty.confidence
            gap.explanation = explanation
            gap.generated_at = now
        else:
            gap = ResumeGapAnalysis(
                resume_id=resume.id,
                role_key=role_key,
                missing_skills=readiness.missing_skills,
                matching_skills=readiness.matching_skills,
                strengths=readiness.strengths,
                focus_areas=readiness.focus_areas,
                recommended_difficulty=difficulty.level,
                difficulty_reasons=difficulty.reasons,
                confidence=difficulty.confidence,
                explanation=explanation,
                generated_at=now,
            )
            self._session.add(gap)

        await self._session.commit()
        logger.info(
            "resume.role_readiness.generated",
            resume_id=str(resume_id),
            role_key=role_key,
            recommended_difficulty=difficulty.level.value,
        )
        return gap


def _sanitize_filename(raw: str | None) -> str:
    """Display-only — never used to build a storage path (see upload()'s
    server-generated storage_key). Strips any path components (defense in
    depth against a client sending "../../etc/passwd.pdf" as the
    multipart filename) and control characters, and caps length.
    """
    name = (raw or "").strip().replace("\\", "/")
    name = name.rsplit("/", 1)[-1]
    name = re.sub(r"[\x00-\x1f\x7f]", "", name).strip()
    return name[:255] if name else "resume.pdf"


def _validate_extension(display_name: str) -> None:
    if not display_name.lower().endswith(".pdf"):
        raise UnprocessableEntityError(
            "Only .pdf files are accepted.", code="UNSUPPORTED_FILE_TYPE"
        )


def _validate_content_type(content_type: str | None) -> None:
    if content_type not in _ALLOWED_UPLOAD_CONTENT_TYPES:
        raise UnprocessableEntityError(
            f"Unsupported content type {content_type!r} — expected application/pdf.",
            code="UNSUPPORTED_MIME_TYPE",
        )
