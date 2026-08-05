"""Background resume-processing job (module §3–§9, §17).

Registered as JOB_HANDLERS["process_resume"] — enqueued once per upload
by the resumes router (app/api/v1/resumes.py, which imports this module
so the registration side-effect actually runs), executed by
BackgroundTasksRunner after the response is sent (Architecture.md §8.1).
Uses its own DB session — the request's session is already torn down by
the time a background task runs — and its own instances of every
collaborator, built via app/services/resume/factories.py the same way
app/api/deps.py builds them for request handlers.

Transaction boundaries (module §17 — "be explicit"):
  1. status -> processing                                        (commit)
  2. deterministic extraction (pdf + sections)
     - scanned/no text: raw_text persisted, status -> failed, STOP  (commit)
     - otherwise: raw_text + detected_sections persisted            (commit)
  3. LLM structured extraction
     - failure/timeout: status -> failed; step 2's commit stands —
       raw_text/detected_sections are never rolled back              (commit)
     - success: children rows persisted, status -> done               (commit)
  4. best-effort ChromaDB indexing — never changes parsed_status either way
"""

import asyncio
from datetime import UTC, datetime

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.session import get_session_factory
from app.jobs.background_tasks_runner import JOB_HANDLERS
from app.models.enums import ParsedStatus, SkillSource
from app.models.resume import (
    Resume,
    ResumeAchievement,
    ResumeCertification,
    ResumeEducation,
    ResumeExperience,
    ResumeProject,
    ResumeSkill,
)
from app.services.resume.date_parsing import parse_loose_date
from app.services.resume.factories import (
    build_embedding_index,
    build_resume_intelligence_provider,
    build_resume_storage,
)
from app.services.resume.pdf import extract_pdf_text
from app.services.resume.section_detection import detect_sections
from app.services.resume.skill_normalization import normalize_skill
from app.services.resume_intelligence.provider import (
    ResumeIntelligenceError,
)
from app.services.resume_intelligence.schemas import ExtractedProfile
from app.vectorstore.resume_embeddings import build_evidence_chunks_from_profile

logger = get_logger(__name__)


async def process_resume_job(*, job_id: str, resume_id: str) -> None:
    settings = get_settings()
    session_factory = get_session_factory()

    async with session_factory() as session:
        resume = await session.get(Resume, resume_id)
        if resume is None:
            logger.warning("resume.process.missing", job_id=job_id, resume_id=resume_id)
            return

        resume.parsed_status = ParsedStatus.PROCESSING
        await session.commit()

        storage = build_resume_storage(settings)
        try:
            content = await storage.read(storage_key=resume.file_url)
        except Exception as exc:  # noqa: BLE001 — storage backend failure, not a resume defect
            logger.error("resume.process.storage_read_failed", resume_id=resume_id, error=str(exc))
            resume.parsed_status = ParsedStatus.FAILED
            resume.processing_error = "Could not read the uploaded file from storage."
            await session.commit()
            return

        # --- Deterministic extraction (module §3) -------------------------
        try:
            # Offloaded — pypdf's per-page text extraction is CPU-bound and
            # would otherwise block this worker's event loop for the
            # duration of parsing (module §17 performance note).
            extraction = await asyncio.to_thread(extract_pdf_text, content)
        except (
            Exception
        ) as exc:  # noqa: BLE001 — upload-time validation already ran; this guards re-parse edge cases
            logger.error("resume.process.extraction_failed", resume_id=resume_id, error=str(exc))
            resume.parsed_status = ParsedStatus.FAILED
            resume.processing_error = f"Text extraction failed: {exc}"
            await session.commit()
            return

        if extraction.is_scanned:
            resume.raw_text = extraction.full_text or None
            resume.parsed_status = ParsedStatus.FAILED
            resume.processing_error = (
                "No extractable text found in this PDF — it looks like a scanned or "
                "image-only document. OCR would be required to process it, and is not "
                "yet supported."
            )
            await session.commit()
            logger.info("resume.process.scanned_pdf", resume_id=resume_id)
            return

        sections = detect_sections(extraction.full_text)
        resume.raw_text = extraction.full_text
        resume.detected_sections = sections
        await session.commit()

        # --- LLM structured extraction (module §5, §8) ---------------------
        try:
            provider = build_resume_intelligence_provider(settings)
            profile = await provider.extract(resume_text=extraction.full_text, sections=sections)
        except ResumeIntelligenceError as exc:
            _mark_ai_failed(resume, f"AI analysis failed: {exc}")
            await session.commit()
            return
        except (
            Exception
        ) as exc:  # noqa: BLE001 — an unexpected provider bug must not corrupt state silently
            logger.error("resume.process.unexpected_ai_error", resume_id=resume_id, error=str(exc))
            _mark_ai_failed(resume, "AI analysis failed unexpectedly.")
            await session.commit()
            return

        _persist_structured_profile(session, resume, profile)
        resume.parsed_status = ParsedStatus.DONE
        resume.processing_error = None
        await session.commit()
        logger.info("resume.process.completed", resume_id=resume_id)

        # --- Best-effort ChromaDB indexing (module §14) ---------------------
        try:
            await _index_embeddings(settings, session, resume)
        except Exception as exc:  # noqa: BLE001 — indexing failure never affects parsed_status
            logger.warning(
                "resume.process.embedding_index_failed", resume_id=resume_id, error=str(exc)
            )


def _mark_ai_failed(resume: Resume, message: str) -> None:
    resume.parsed_status = ParsedStatus.FAILED
    resume.processing_error = message
    logger.warning("resume.process.ai_failed", resume_id=str(resume.id), message=message)


def _persist_structured_profile(session, resume: Resume, profile: ExtractedProfile) -> None:
    resume.candidate_name = profile.candidate_name
    resume.professional_summary = profile.professional_summary

    seen_canonical_names: set[str] = set()
    for item in profile.skills:
        normalized = normalize_skill(item.name)
        key = normalized.canonical.lower()
        if key in seen_canonical_names:
            # Same canonical skill mentioned twice (e.g. once in Skills,
            # once inferred from a project) — keep the first evidence
            # found rather than duplicating the row.
            continue
        seen_canonical_names.add(key)
        source = SkillSource.EXPLICIT if item.source == "explicit" else SkillSource.INFERRED
        session.add(
            ResumeSkill(
                resume_id=resume.id,
                skill_name=normalized.canonical,
                source=source,
                category=normalized.category,
                raw_text=item.name,
                evidence_text=item.evidence,
            )
        )

    for edu in profile.education:
        session.add(
            ResumeEducation(
                resume_id=resume.id,
                institution=edu.institution,
                degree=edu.degree,
                field_of_study=edu.field_of_study,
                start_date=parse_loose_date(edu.start_date),
                end_date=parse_loose_date(edu.end_date),
                evidence_text=edu.evidence,
            )
        )

    for proj in profile.projects:
        session.add(
            ResumeProject(
                resume_id=resume.id,
                title=proj.title,
                description=proj.description,
                technologies=proj.technologies,
                responsibilities=proj.responsibilities,
                outcomes=proj.outcomes,
                start_date=parse_loose_date(proj.start_date),
                end_date=parse_loose_date(proj.end_date),
                evidence_text=proj.evidence,
            )
        )

    for exp in profile.experience:
        session.add(
            ResumeExperience(
                resume_id=resume.id,
                company=exp.company,
                title=exp.title,
                description=exp.description,
                technologies=exp.technologies,
                responsibilities=exp.responsibilities,
                start_date=parse_loose_date(exp.start_date),
                end_date=parse_loose_date(exp.end_date),
                evidence_text=exp.evidence,
            )
        )

    for cert in profile.certifications:
        session.add(
            ResumeCertification(
                resume_id=resume.id,
                name=cert.name,
                issuer=cert.issuer,
                issued_date=parse_loose_date(cert.issued_date),
                evidence_text=cert.evidence,
            )
        )

    for ach in profile.achievements:
        session.add(
            ResumeAchievement(
                resume_id=resume.id, description=ach.description, evidence_text=ach.evidence
            )
        )


async def _index_embeddings(settings, session, resume: Resume) -> None:
    await session.refresh(
        resume, attribute_names=["skills", "projects", "experience", "certifications"]
    )
    skills = [(s.skill_name, s.evidence_text) for s in resume.skills]
    projects = [(p.title, p.evidence_text or p.description) for p in resume.projects]
    experience = [
        (f"{e.company} - {e.title}", e.evidence_text or e.description) for e in resume.experience
    ]
    certifications = [(c.name, c.evidence_text) for c in resume.certifications]

    chunks = build_evidence_chunks_from_profile(
        skills=skills, projects=projects, experience=experience, certifications=certifications
    )
    index = build_embedding_index(settings)
    await index.reindex_resume(user_id=resume.user_id, resume_id=resume.id, chunks=chunks)
    resume.embeddings_indexed_at = datetime.now(UTC)
    await session.commit()


JOB_HANDLERS["process_resume"] = process_resume_job
