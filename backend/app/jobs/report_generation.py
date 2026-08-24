"""Background report-generation job (Module 7) — the ONLY place a
session's report/roadmap is actually produced. Registered as
JOB_HANDLERS["generate_report"] (imported by app/api/v1/reports.py so the
registration side-effect actually runs, mirroring app/jobs/
coding_execution.py's exact pattern).

Two distinct trigger paths reach this same function (decision #1 — report
generation is durable background work, never inline on the Gemini call
path):
  - app/api/v1/interviews.py's submit_answer handler, a live request with
    a real BackgroundTasks — enqueues this job normally via JobRunner.
  - app/jobs/coding_execution.py's run_code_submission_job, itself
    already running as a background task with no live BackgroundTasks to
    enqueue onto (and no persistent queue exists yet in this codebase —
    Roadmap.md's Celery work is Module 9) — calls this function directly
    by await instead. Either way the function itself is identical: its
    own DB session, its own provider instance, one commit.

No retry/backoff — matches coding_execution.py's/resume_processing.py's
established "log and stop" pattern for job failures. A failure here
(Gemini timeout/error, DB error) leaves zero report rows written
(ReportService.generate_report_for_session's own docstring covers why);
GET /interview-sessions/{id}/report surfaces this as
"REPORT_NOT_YET_AVAILABLE" rather than fabricating a partial report.

Module 8's one approved integration point (Database.md §8:
`user_progress_snapshots` is "written whenever a report is generated"):
right after a real report is committed, ProgressService.record_session_progress
runs in this *same* session/transaction — no separate job, no LLM call,
just deterministic aggregation, so there's nothing here that needs its own
background-task scheduling the way report generation itself did. Wrapped
in its own try/except: a progress-recording bug must never retroactively
void an already-correct, already-committed report.
"""

import uuid

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.session import get_session_factory
from app.jobs.background_tasks_runner import JOB_HANDLERS
from app.services.progress.progress_service import ProgressService
from app.services.report.report_service import ReportService
from app.services.report_generation.factories import build_report_generation_provider

logger = get_logger(__name__)


async def generate_report_job(*, job_id: str, interview_id: str, user_id: str) -> None:
    settings = get_settings()
    session_factory = get_session_factory()

    async with session_factory() as session:
        service = ReportService(session)
        provider = build_report_generation_provider(settings)
        try:
            report = await service.generate_report_for_session(
                uuid.UUID(interview_id), user_id=uuid.UUID(user_id), provider=provider
            )
        except Exception as exc:  # noqa: BLE001 — report generation must never crash silently
            logger.error(
                "report.job.generation_failed",
                job_id=job_id,
                interview_id=interview_id,
                error=str(exc),
            )
            return
        logger.info(
            "report.job.completed",
            job_id=job_id,
            interview_id=interview_id,
            report_id=str(report.id) if report else None,
        )

        if report is not None:
            try:
                await ProgressService(session).record_session_progress(
                    report, user_id=uuid.UUID(user_id)
                )
            except Exception as exc:  # noqa: BLE001 — must never void an already-valid report
                logger.error(
                    "progress.job.record_failed",
                    job_id=job_id,
                    interview_id=interview_id,
                    error=str(exc),
                )
            else:
                logger.info("progress.job.recorded", job_id=job_id, interview_id=interview_id)


JOB_HANDLERS["generate_report"] = generate_report_job
