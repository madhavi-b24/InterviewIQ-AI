"""CodingRoundService — Module 6's coding-round use case: the candidate-
facing Run/Submit lifecycle for a coding Question. Entirely separate from
InterviewExecutionService's turn-based graph flow (module §9 — Run/Submit
are plain service calls, never LangGraph turns; LangGraph only ever picks
WHICH problem a round presents, via select_coding_problem_node).

Two-phase idempotent pattern (mirrors
InterviewExecutionService.submit_answer, module §22):
  - `create_submission` durably persists the CodeSubmission row (QUEUED)
    and enqueues the actual execution as a background job BEFORE any
    execution/evaluation happens — the candidate's submitted code
    survives even if the sandbox call or Gemini evaluation later fails.
  - `execute_and_grade_submission` (called by the job, app/jobs/
    coding_execution.py, never by a request handler — module §17's "don't
    run unbounded execution directly in the request lifecycle") does the
    expensive work and commits the result; polled via `get_submission`.

Run vs Submit (module §6): both call `create_submission`. is_final=False
(Run) only ever executes the question's SAMPLE test cases and never calls
CodeEvaluationProvider. is_final=True (Submit) executes ALL test cases and
triggers CodeEvaluationProvider — exactly once per question. The DB's
`ux_code_submissions_final` partial unique index (Module 1 baseline, not
reopened here) is the concurrency backstop; `is_final` is set at creation
time (a durable reservation, same two-phase spirit as above) and only
released back to False if grading never reaches a genuine verdict because
OUR infrastructure failed (never for the candidate's own compile/runtime/
timeout outcome, which IS a genuine, final verdict) — see
`_release_final_slot_on_infra_failure`'s docstring for the full reasoning.

Multi-attempt (module §6): every attempt is a new CodeSubmission row
(attempt_no incrementing) — a Run never overwrites a prior attempt.

Async-session discipline: every read in this module either comes from an
explicit repository query or a plain scalar column (`submission.answer_id`,
never `submission.answer`) — relationship attributes are never accessed
after a commit, which expires them and would trigger an implicit lazy
load (MissingGreenlet under asyncpg — see
app/services/coding/catalog_seed.py's module docstring for the same trap
hit and fixed earlier in this module).
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.policy import compute_overall_code_score
from app.core.exceptions import ConflictError, NotFoundError, UnprocessableEntityError
from app.core.logging import get_logger
from app.execution.base import CodeExecutor, ExecutionOutcome, TestCase, TestCaseResult
from app.execution.exceptions import CodeExecutionError
from app.jobs.base import JobRunner
from app.models.enums import CodeExecutionStatus, QuestionType
from app.models.evaluation import CodingEvaluation
from app.models.interview import Answer, CodeSubmission, CodeSubmissionTestResult, Question
from app.models.interview import QuestionTestCase as QuestionTestCaseModel
from app.repositories.coding import CodeSubmissionRepository, CodingEvaluationRepository
from app.repositories.interview import (
    AnswerRepository,
    InterviewSessionRepository,
    QuestionRepository,
    QuestionTestCaseRepository,
)
from app.services.code_evaluation.provider import CodeEvaluationError, CodeEvaluationProvider

logger = get_logger(__name__)

# Job name registered in app/jobs/coding_execution.py's JOB_HANDLERS —
# named here once so create_submission and the job registration never
# drift out of sync with a hand-typed string in two places.
RUN_CODE_SUBMISSION_JOB = "run_code_submission"


class CodingRoundService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._interviews = InterviewSessionRepository(session)
        self._questions = QuestionRepository(session)
        self._test_cases = QuestionTestCaseRepository(session)
        self._answers = AnswerRepository(session)
        self._submissions = CodeSubmissionRepository(session)
        self._evaluations = CodingEvaluationRepository(session)

    # --- Reads -----------------------------------------------------------

    async def get_coding_question(
        self, *, interview_id: uuid.UUID, user_id: uuid.UUID, question_id: uuid.UUID
    ) -> Question:
        return await self._owned_coding_question(
            interview_id=interview_id, user_id=user_id, question_id=question_id
        )

    async def get_submission(
        self, *, interview_id: uuid.UUID, user_id: uuid.UUID, submission_id: uuid.UUID
    ) -> CodeSubmission:
        submission = await self._submissions.get_with_test_results(submission_id)
        if submission is None:
            raise NotFoundError("code submission not found", code="CODE_SUBMISSION_NOT_FOUND")
        await self._verify_submission_ownership(
            submission, interview_id=interview_id, user_id=user_id
        )
        return submission

    async def list_submissions_for_question(
        self, *, interview_id: uuid.UUID, user_id: uuid.UUID, question_id: uuid.UUID
    ) -> list[CodeSubmission]:
        question = await self._owned_coding_question(
            interview_id=interview_id, user_id=user_id, question_id=question_id
        )
        answer = await self._answers.get_by_question_id(question.id)
        if answer is None:
            return []
        return await self._submissions.list_for_answer(answer.id)

    async def get_evaluation(
        self, *, interview_id: uuid.UUID, user_id: uuid.UUID, submission_id: uuid.UUID
    ) -> CodingEvaluation | None:
        submission = await self.get_submission(
            interview_id=interview_id, user_id=user_id, submission_id=submission_id
        )
        return await self._evaluations.get_by_submission_id(submission.id)

    # --- Create (Phase 1: durable, cheap, before any execution) ----------

    async def create_submission(
        self,
        *,
        interview_id: uuid.UUID,
        user_id: uuid.UUID,
        question_id: uuid.UUID,
        language: str,
        source_code: str,
        is_final: bool,
        job_runner: JobRunner,
    ) -> CodeSubmission:
        question = await self._owned_coding_question(
            interview_id=interview_id, user_id=user_id, question_id=question_id
        )
        supported = (question.coding_snapshot or {}).get("supported_languages", [])
        if supported and language not in supported:
            raise UnprocessableEntityError(
                f"language {language!r} is not supported for this problem "
                f"(supported: {', '.join(supported)})",
                code="UNSUPPORTED_LANGUAGE",
            )

        answer = await self._answers.get_by_question_id(question.id)
        if answer is None:
            answer = Answer(
                question_id=question.id, answer_text=None, submitted_at=datetime.now(UTC)
            )
            await self._answers.add(answer)
        # Captured as a plain value now, not re-read off `answer` later —
        # `await self._session.rollback()` below (on the IntegrityError
        # race path) expires every ORM object in the session, and a
        # synchronous `answer.id` read on an expired object triggers an
        # implicit refresh that is unsafe under the async engine
        # (MissingGreenlet — the exact trap app/services/coding/
        # catalog_seed.py's module docstring already documents once).
        answer_id = answer.id

        if is_final:
            existing_final = await self._submissions.get_final_for_answer(answer_id)
            if existing_final is not None:
                if existing_final.execution_status in (
                    CodeExecutionStatus.QUEUED,
                    CodeExecutionStatus.RUNNING,
                ):
                    raise ConflictError(
                        "a final submission for this question is already being graded",
                        code="FINAL_SUBMISSION_IN_PROGRESS",
                    )
                logger.info(
                    "coding.submission.final_idempotent_replay",
                    interview_id=str(interview_id),
                    question_id=str(question_id),
                )
                return existing_final

        attempt_no = await self._submissions.next_attempt_no(answer_id)
        submission = CodeSubmission(
            answer_id=answer_id,
            attempt_no=attempt_no,
            is_final=is_final,
            language=language,
            source_code=source_code,
            execution_status=CodeExecutionStatus.QUEUED,
        )
        try:
            await self._submissions.add(submission)
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            # Two concurrent requests raced past the pre-checks above —
            # the DB's own constraints are the real backstop (module §22):
            # (answer_id, attempt_no) for a Run race, or
            # ux_code_submissions_final for a Submit race.
            if is_final:
                existing_final = await self._submissions.get_final_for_answer(answer_id)
                if existing_final is not None:
                    logger.warning(
                        "coding.submission.final_race_detected",
                        interview_id=str(interview_id),
                        question_id=str(question_id),
                    )
                    return existing_final
            raise ConflictError(
                "a concurrent submission for this question was already recorded — retry to "
                "fetch its result",
                code="CODE_SUBMISSION_RACE",
            ) from exc

        job_runner.enqueue(RUN_CODE_SUBMISSION_JOB, {"submission_id": str(submission.id)})
        logger.info(
            "coding.submission.created",
            interview_id=str(interview_id),
            question_id=str(question_id),
            submission_id=str(submission.id),
            attempt_no=attempt_no,
            is_final=is_final,
        )
        return submission

    # --- Grading (Phase 2 — called by the job, never by a request) -------

    async def execute_and_grade_submission(
        self,
        *,
        submission_id: uuid.UUID,
        executor: CodeExecutor,
        evaluation_provider: CodeEvaluationProvider,
    ) -> CodeSubmission | None:
        """The job body. Owns the full execute -> score -> (final-only)
        evaluate -> persist pipeline for exactly one submission. Returns
        the updated CodeSubmission, or None if it was already terminal
        (idempotent no-op — defends against a hypothetical duplicate job
        invocation, module §22).
        """
        submission = await self._submissions.get_by_id(submission_id)
        if submission is None:
            logger.warning("coding.grade.missing_submission", submission_id=str(submission_id))
            return None
        if submission.execution_status not in (
            CodeExecutionStatus.QUEUED,
            CodeExecutionStatus.RUNNING,
        ):
            logger.info(
                "coding.grade.already_terminal",
                submission_id=str(submission_id),
                execution_status=submission.execution_status.value,
            )
            return submission

        answer = await self._answers.get_by_id(submission.answer_id)
        question = await self._questions.get_by_id(answer.question_id) if answer else None
        if question is None:
            logger.error("coding.grade.missing_question", submission_id=str(submission_id))
            return submission

        all_test_cases = await self._test_cases.list_for_question(question.id)
        # Run: sample-only (module §6). Submit: everything.
        test_cases = (
            all_test_cases if submission.is_final else [tc for tc in all_test_cases if tc.is_sample]
        )
        if not test_cases:
            logger.error("coding.grade.no_test_cases", submission_id=str(submission_id))
            submission.execution_status = CodeExecutionStatus.ERROR
            submission.error_message = "This problem has no test cases configured."
            _release_final_slot_on_infra_failure(submission)
            await self._session.commit()
            return submission

        submission.execution_status = CodeExecutionStatus.RUNNING
        await self._session.commit()

        try:
            outcome = await executor.run(
                source_code=submission.source_code,
                language=submission.language,
                test_cases=[
                    TestCase(
                        id=str(tc.id),
                        input=tc.input,
                        expected_output=tc.expected_output,
                        is_sample=tc.is_sample,
                        weight=float(tc.weight),
                    )
                    for tc in test_cases
                ],
            )
        except CodeExecutionError as exc:
            # Genuine sandbox/infra failure — never the candidate's fault,
            # never a real verdict. Release the final slot (see module
            # docstring) so a retry is possible.
            logger.error(
                "coding.grade.executor_failed", submission_id=str(submission_id), error=str(exc)
            )
            submission.execution_status = CodeExecutionStatus.ERROR
            submission.error_message = f"Execution failed: {exc}"
            _release_final_slot_on_infra_failure(submission)
            await self._session.commit()
            return submission

        passed_ids = _persist_execution_outcome(submission, test_cases, outcome, self._session)
        await self._session.commit()

        if not submission.is_final:
            logger.info(
                "coding.grade.run_completed",
                submission_id=str(submission_id),
                execution_status=submission.execution_status.value,
            )
            return submission

        # --- Submit-only: LLM code-quality evaluation ----------------------
        if submission.execution_status == CodeExecutionStatus.COMPILE_ERROR:
            # Nothing ran — there is no code behavior to judge quality of
            # beyond "it doesn't compile." correctness_score=0, no LLM call
            # (module §10: never spend an LLM call the outcome doesn't need).
            _add_zero_evaluation(self._session, submission, reason="Submission failed to compile.")
            await self._session.commit()
            return submission

        correctness_score = _weighted_correctness(test_cases, submission, passed_ids)
        try:
            result = await evaluation_provider.evaluate(
                problem_title=(question.coding_snapshot or {}).get("title", question.topic),
                problem_description=question.question_text,
                language=submission.language,
                source_code=submission.source_code,
                passed_test_count=submission.passed_test_count or 0,
                total_test_count=submission.total_test_count or len(test_cases),
            )
        except CodeEvaluationError as exc:
            logger.error(
                "coding.grade.evaluation_failed", submission_id=str(submission_id), error=str(exc)
            )
            # Execution genuinely succeeded and IS a real verdict — but
            # without the LLM's qualitative judgment, grading isn't
            # complete. Release the final slot so the candidate can submit
            # again once the evaluation provider recovers, rather than
            # being left with a permanently half-graded submission.
            submission.error_message = f"Code quality evaluation failed: {exc}"
            _release_final_slot_on_infra_failure(submission)
            await self._session.commit()
            return submission

        overall = compute_overall_code_score(
            correctness_score=correctness_score,
            readability_score=result.readability_score,
            optimization_score=result.optimization_score,
            edge_case_score=result.edge_case_score,
        )
        self._session.add(
            CodingEvaluation(
                code_submission_id=submission.id,
                correctness_score=correctness_score,
                correctness_explanation=(
                    f"{submission.passed_test_count}/{submission.total_test_count} "
                    "test cases passed (weighted)."
                ),
                time_complexity=result.time_complexity,
                space_complexity=result.space_complexity,
                readability_score=result.readability_score,
                readability_explanation=result.readability_explanation,
                optimization_score=result.optimization_score,
                optimization_explanation=result.optimization_explanation,
                edge_case_score=result.edge_case_score,
                edge_case_explanation=result.edge_case_explanation,
                overall_code_score=overall,
                strengths=result.strengths,
                weaknesses=result.weaknesses,
                recommendations=result.recommendations,
            )
        )
        submission.graded_at = datetime.now(UTC)
        await self._session.commit()
        logger.info(
            "coding.grade.submit_completed",
            submission_id=str(submission_id),
            overall_code_score=overall,
        )
        return submission

    # --- Internals ---------------------------------------------------------

    async def _owned_coding_question(
        self, *, interview_id: uuid.UUID, user_id: uuid.UUID, question_id: uuid.UUID
    ) -> Question:
        interview = await self._interviews.get_owned(interview_id, user_id)
        if interview is None:
            raise NotFoundError("interview not found", code="INTERVIEW_NOT_FOUND")
        question = await self._questions.get_with_round(question_id)
        if (
            question is None
            or question.question_type != QuestionType.CODING
            or question.round.session_id != interview.id
        ):
            raise NotFoundError("coding question not found", code="CODING_QUESTION_NOT_FOUND")
        return question

    async def _verify_submission_ownership(
        self, submission: CodeSubmission, *, interview_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        interview = await self._interviews.get_owned(interview_id, user_id)
        if interview is None:
            raise NotFoundError("interview not found", code="INTERVIEW_NOT_FOUND")
        answer = await self._answers.get_by_id(submission.answer_id)
        question = await self._questions.get_with_round(answer.question_id) if answer else None
        if question is None or question.round.session_id != interview.id:
            raise NotFoundError("code submission not found", code="CODE_SUBMISSION_NOT_FOUND")


def _release_final_slot_on_infra_failure(submission: CodeSubmission) -> None:
    """Only OUR infrastructure failing (sandbox unreachable, evaluation
    provider down) ever calls this — never a candidate outcome
    (compile/runtime/timeout/wrong-answer are all genuine, final verdicts,
    module docstring). Releasing `is_final` frees the DB's partial unique
    slot so a retry can create a fresh final submission.
    """
    if submission.is_final:
        submission.is_final = False


def _persist_execution_outcome(
    submission: CodeSubmission,
    test_cases: list[QuestionTestCaseModel],
    outcome: ExecutionOutcome,
    session: AsyncSession,
) -> set[str]:
    """Persists one CodeSubmissionTestResult row per test case, sets the
    submission's aggregate execution_status/counts, and returns the set of
    passed test_case ids (as strings) — handed back to the caller instead
    of being re-read via `submission.test_results` afterward, which would
    be expired post-commit and trigger a lazy load (module docstring).
    """
    if not outcome.compiled:
        submission.execution_status = CodeExecutionStatus.COMPILE_ERROR
        submission.error_message = outcome.compile_message
        submission.passed_test_count = 0
        submission.total_test_count = len(test_cases)
        return set()

    results_by_id: dict[str, TestCaseResult] = {r.test_case_id: r for r in outcome.results}
    passed_count = 0
    passed_ids: set[str] = set()
    total_runtime_ms = 0
    any_timed_out = False
    any_output_truncated = False
    any_crashed = False

    for tc in test_cases:
        result = results_by_id.get(str(tc.id))
        if result is None:
            continue
        session.add(
            CodeSubmissionTestResult(
                code_submission_id=submission.id,
                test_case_id=tc.id,
                passed=result.passed,
                actual_output=result.actual_output,
                runtime_ms=result.runtime_ms,
                memory_kb=result.memory_kb,
                stderr=result.stderr,
            )
        )
        if result.passed:
            passed_count += 1
            passed_ids.add(str(tc.id))
        total_runtime_ms += result.runtime_ms or 0
        any_timed_out = any_timed_out or result.timed_out
        any_output_truncated = any_output_truncated or result.output_truncated
        if not result.passed and not result.timed_out and result.exit_code not in (0, None):
            any_crashed = True

    submission.passed_test_count = passed_count
    submission.total_test_count = len(test_cases)
    submission.total_runtime_ms = total_runtime_ms

    # Aggregate precedence (module §7): worst signal across all test cases
    # wins, so the candidate sees the single most informative status.
    if any_timed_out:
        submission.execution_status = CodeExecutionStatus.TIMEOUT  # = module §7's TIME_LIMIT
    elif any_output_truncated:
        submission.execution_status = CodeExecutionStatus.OUTPUT_LIMIT
    elif any_crashed:
        submission.execution_status = CodeExecutionStatus.RUNTIME_ERROR
    elif passed_count == len(test_cases):
        submission.execution_status = CodeExecutionStatus.SUCCESS
    else:
        submission.execution_status = CodeExecutionStatus.PARTIAL

    return passed_ids


def _weighted_correctness(
    test_cases: list[QuestionTestCaseModel], submission: CodeSubmission, passed_ids: set[str]
) -> float:
    """0-100, weighted by each QuestionTestCase's own `weight` column
    (Database.md's existing design for exactly this) — distinct from the
    simple unweighted passed_test_count/total_test_count shown to the
    candidate.
    """
    total_weight = sum(float(tc.weight) for tc in test_cases)
    if total_weight <= 0:
        return 0.0
    if submission.execution_status == CodeExecutionStatus.SUCCESS:
        return 100.0
    passed_weight = sum(float(tc.weight) for tc in test_cases if str(tc.id) in passed_ids)
    return round(100.0 * passed_weight / total_weight, 2)


def _add_zero_evaluation(session: AsyncSession, submission: CodeSubmission, *, reason: str) -> None:
    session.add(
        CodingEvaluation(
            code_submission_id=submission.id,
            correctness_score=0.0,
            correctness_explanation=reason,
            time_complexity=None,
            space_complexity=None,
            readability_score=0.0,
            readability_explanation=reason,
            optimization_score=0.0,
            optimization_explanation=reason,
            edge_case_score=0.0,
            edge_case_explanation=reason,
            overall_code_score=0.0,
            strengths=[],
            weaknesses=[reason],
            recommendations=["Fix the compilation error and submit again."],
        )
    )
    submission.graded_at = datetime.now(UTC)
