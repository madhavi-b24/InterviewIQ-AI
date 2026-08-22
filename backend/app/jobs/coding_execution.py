"""Background code-execution job (Module 6, module §17) — the ONLY place
a code submission is actually run and graded. Registered as
JOB_HANDLERS["run_code_submission"] (imported by app/api/v1/code_submissions.py
so the registration side-effect actually runs, mirroring
app/jobs/resume_processing.py's exact pattern), executed by
BackgroundTasksRunner after the response is sent — CodingRoundService.
create_submission has already durably persisted the QUEUED row and
committed before this job even starts (module §22: the candidate's code
is never lost even if this job crashes outright).

Uses its own DB session and its own executor/evaluation-provider
instances — built via app/execution/factories.py and
app/services/code_evaluation/factories.py, the same way
app/api/deps.py builds them for request handlers — since a background
task has no request-scoped FastAPI dependency injection (identical
reasoning to resume_processing.py's own module docstring).

After grading, a *final* submission that reached a real terminal outcome
(SUCCESS/PARTIAL/COMPILE_ERROR/RUNTIME_ERROR/TIME_LIMIT/OUTPUT_LIMIT — a
genuine verdict, never a bare infra ERROR) advances the interview to its
next round via InterviewExecutionService.complete_coding_round, using the
CODING_ROUND_COMPLETE trigger (module §9). A Run, or a Submit that failed
at the infrastructure level (is_final released back to False by
CodingRoundService), never touches round advancement at all.
"""

import uuid

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.session import get_session_factory
from app.execution.factories import build_code_executor
from app.jobs.background_tasks_runner import JOB_HANDLERS
from app.models.enums import CodeExecutionStatus
from app.models.interview import Answer, InterviewRound, InterviewSession, Question
from app.services.code_evaluation.factories import build_code_evaluation_provider
from app.services.coding.coding_round_service import CodingRoundService
from app.services.interview.execution_service import InterviewExecutionService
from app.services.interview_intelligence.factories import build_interview_agent_provider

logger = get_logger(__name__)

# A submission that reached one of these after grading represents a real,
# final verdict on the candidate's code — the round is done, whatever the
# outcome. A bare ERROR (infra failure) is deliberately excluded: those
# have `is_final` released back to False by CodingRoundService, so no
# round-completion should ever be attempted for them.
_GRADED_TERMINAL_STATUSES = frozenset(
    {
        CodeExecutionStatus.SUCCESS,
        CodeExecutionStatus.PARTIAL,
        CodeExecutionStatus.COMPILE_ERROR,
        CodeExecutionStatus.RUNTIME_ERROR,
        CodeExecutionStatus.TIMEOUT,  # = module §7's TIME_LIMIT (app/models/enums.py)
        CodeExecutionStatus.OUTPUT_LIMIT,
    }
)


async def run_code_submission_job(*, job_id: str, submission_id: str) -> None:
    settings = get_settings()
    session_factory = get_session_factory()

    async with session_factory() as session:
        service = CodingRoundService(session)
        executor = build_code_executor(settings)
        evaluation_provider = build_code_evaluation_provider(settings)

        submission = await service.execute_and_grade_submission(
            submission_id=uuid.UUID(submission_id),
            executor=executor,
            evaluation_provider=evaluation_provider,
        )
        if submission is None:
            logger.warning("coding.job.submission_missing", job_id=job_id)
            return

        if not (submission.is_final and submission.execution_status in _GRADED_TERMINAL_STATUSES):
            return

        # --- Advance the interview to its next round ------------------------
        # Plain session.get() chases through Answer -> Question ->
        # InterviewRound -> InterviewSession by scalar FK column only
        # (never a relationship attribute) — every one of these is a
        # simple primary-key lookup, no join/query-builder needed.
        answer = await session.get(Answer, submission.answer_id)
        question = await session.get(Question, answer.question_id)
        interview_round = await session.get(InterviewRound, question.round_id)
        interview = await session.get(InterviewSession, interview_round.session_id)

        provider = build_interview_agent_provider(settings)
        execution_service = InterviewExecutionService(session)
        try:
            await execution_service.complete_coding_round(
                interview_id=interview.id,
                user_id=interview.user_id,
                question_id=question.id,
                provider=provider,
            )
        except Exception as exc:  # noqa: BLE001 — a round-advancement bug must not crash silently
            logger.error(
                "coding.job.round_advance_failed",
                job_id=job_id,
                submission_id=submission_id,
                error=str(exc),
            )
        else:
            logger.info(
                "coding.job.round_advanced",
                job_id=job_id,
                submission_id=submission_id,
                interview_id=str(interview.id),
            )


JOB_HANDLERS["run_code_submission"] = run_code_submission_job
