"""Coding round API — Module 6. New sub-resource endpoints under
/interview-sessions/{interview_id}, mirroring interviews.py's own
docstring convention ("Module N adds routes to this same router file" —
here as a sibling module, since this is a big enough surface to deserve
its own file, still registered onto the same `interviews_router` prefix
via app/api/v1/router.py).

Thin per Architecture.md §4: parses the request, calls exactly one
CodingRoundService method, shapes the response. No SQLAlchemy or
execution/sandbox logic lives here — Run/Submit both just persist +
enqueue (module §17: never run unbounded execution in the request
lifecycle) and return immediately; the candidate polls
GET .../code-submissions/{id} for the graded result.

Hidden test cases never leave this boundary — see app/schemas/coding.py's
module docstring; `_submission_out`/`_problem_out` below are the only
places a CodeSubmission/Question ever gets shaped into a response, and
neither ever touches a non-sample QuestionTestCase's input/expected_output.
"""

import uuid

from fastapi import APIRouter, status

import app.jobs.coding_execution  # noqa: F401 — import registers JOB_HANDLERS["run_code_submission"]
from app.api.deps import CodingRoundServiceDep, CurrentUser, JobRunnerDep
from app.models.interview import CodeSubmission, Question
from app.schemas.coding import (
    CodeSubmissionOut,
    CodeSubmissionRequest,
    CodeSubmissionTestResultOut,
    CodingEvaluationOut,
    CodingProblemOut,
    CodingSampleTestCaseOut,
)

router = APIRouter(prefix="/interview-sessions", tags=["coding"])


@router.get("/{interview_id}/questions/{question_id}/coding-problem")
async def get_coding_problem(
    interview_id: uuid.UUID,
    question_id: uuid.UUID,
    current_user: CurrentUser,
    coding: CodingRoundServiceDep,
) -> CodingProblemOut:
    question = await coding.get_coding_question(
        interview_id=interview_id, user_id=current_user.id, question_id=question_id
    )
    return _problem_out(question)


@router.post(
    "/{interview_id}/questions/{question_id}/code-submissions", status_code=status.HTTP_202_ACCEPTED
)
async def create_code_submission(
    interview_id: uuid.UUID,
    question_id: uuid.UUID,
    data: CodeSubmissionRequest,
    current_user: CurrentUser,
    coding: CodingRoundServiceDep,
    job_runner: JobRunnerDep,
) -> CodeSubmissionOut:
    created = await coding.create_submission(
        interview_id=interview_id,
        user_id=current_user.id,
        question_id=question_id,
        language=data.language,
        source_code=data.source_code,
        is_final=data.is_final,
        job_runner=job_runner,
    )
    # Re-fetched via get_submission (eager-loads test_results/answer/
    # test_case) rather than shaping `created` directly — a freshly
    # flushed object's un-eager-loaded collection would otherwise trigger
    # an implicit lazy load (MissingGreenlet under asyncpg). This also
    # means the response body — built before BackgroundTasks run the
    # grading job (module §17) — always genuinely reflects this exact
    # moment's DB state (QUEUED, or an existing final submission's already
    # -graded state on an idempotent replay), never a stale in-memory copy.
    submission = await coding.get_submission(
        interview_id=interview_id, user_id=current_user.id, submission_id=created.id
    )
    return _submission_out(submission)


@router.get("/{interview_id}/questions/{question_id}/code-submissions")
async def list_code_submissions(
    interview_id: uuid.UUID,
    question_id: uuid.UUID,
    current_user: CurrentUser,
    coding: CodingRoundServiceDep,
) -> list[CodeSubmissionOut]:
    submissions = await coding.list_submissions_for_question(
        interview_id=interview_id, user_id=current_user.id, question_id=question_id
    )
    return [_submission_out(s) for s in submissions]


@router.get("/{interview_id}/code-submissions/{submission_id}")
async def get_code_submission(
    interview_id: uuid.UUID,
    submission_id: uuid.UUID,
    current_user: CurrentUser,
    coding: CodingRoundServiceDep,
) -> CodeSubmissionOut:
    submission = await coding.get_submission(
        interview_id=interview_id, user_id=current_user.id, submission_id=submission_id
    )
    return _submission_out(submission)


@router.get("/{interview_id}/code-submissions/{submission_id}/evaluation")
async def get_code_evaluation(
    interview_id: uuid.UUID,
    submission_id: uuid.UUID,
    current_user: CurrentUser,
    coding: CodingRoundServiceDep,
) -> CodingEvaluationOut | None:
    evaluation = await coding.get_evaluation(
        interview_id=interview_id, user_id=current_user.id, submission_id=submission_id
    )
    if evaluation is None:
        return None
    return CodingEvaluationOut(
        correctness_score=float(evaluation.correctness_score),
        correctness_explanation=evaluation.correctness_explanation,
        readability_score=float(evaluation.readability_score),
        readability_explanation=evaluation.readability_explanation,
        optimization_score=float(evaluation.optimization_score),
        optimization_explanation=evaluation.optimization_explanation,
        edge_case_score=float(evaluation.edge_case_score),
        edge_case_explanation=evaluation.edge_case_explanation,
        time_complexity=evaluation.time_complexity,
        space_complexity=evaluation.space_complexity,
        overall_code_score=float(evaluation.overall_code_score),
        strengths=evaluation.strengths,
        weaknesses=evaluation.weaknesses,
        recommendations=evaluation.recommendations,
    )


def _problem_out(question: Question) -> CodingProblemOut:
    snapshot = question.coding_snapshot or {}
    sample_tests = [
        CodingSampleTestCaseOut(input=tc.input, expected_output=tc.expected_output)
        for tc in question.test_cases
        if tc.is_sample
    ]
    return CodingProblemOut(
        question_id=question.id,
        title=snapshot.get("title", question.topic),
        description=question.question_text,
        difficulty=question.difficulty,
        topics=snapshot.get("topics", []),
        constraints=snapshot.get("constraints"),
        expected_time_complexity=snapshot.get("expected_time_complexity"),
        expected_space_complexity=snapshot.get("expected_space_complexity"),
        supported_languages=snapshot.get("supported_languages", []),
        starter_code=snapshot.get("starter_code", {}),
        sample_test_cases=sample_tests,
    )


def _submission_out(submission: CodeSubmission) -> CodeSubmissionOut:
    # test_results/answer/test_case are all eager-loaded by
    # CodeSubmissionRepository (app/repositories/coding.py's
    # _SUBMISSION_LOAD_OPTIONS) for every code path this function is
    # reached from — never lazy-loaded here. Only sample test cases'
    # results are itemized (module §8); hidden ones only ever contribute
    # to the aggregate counts already on the submission row.
    sample_results = [
        CodeSubmissionTestResultOut(
            input=r.test_case.input,
            expected_output=r.test_case.expected_output,
            actual_output=r.actual_output,
            passed=r.passed,
            runtime_ms=r.runtime_ms,
            stderr=r.stderr,
        )
        for r in submission.test_results
        if r.test_case.is_sample
    ]
    return CodeSubmissionOut(
        id=submission.id,
        question_id=submission.answer.question_id,
        attempt_no=submission.attempt_no,
        is_final=submission.is_final,
        language=submission.language,
        execution_status=submission.execution_status,
        passed_test_count=submission.passed_test_count,
        total_test_count=submission.total_test_count,
        total_runtime_ms=submission.total_runtime_ms,
        error_message=submission.error_message,
        sample_test_results=sample_results,
        created_at=submission.created_at,
        graded_at=submission.graded_at,
    )
