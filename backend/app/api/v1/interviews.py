"""Interview session API — API.md §4. Planning endpoints (`POST`/`GET
/interview-sessions`, `GET /interview-sessions/{id}/plan`) are Module 4;
execution endpoints (`/start`, `/current-turn`, `/answers`, `/abandon`)
are Module 5, added here per the Module 4 router's own docstring ("Module
5 adds new routes to this same router file").

Thin per Architecture.md §4: parses the request, calls exactly one
service method (InterviewPlannerService or InterviewExecutionService),
shapes the response. No SQLAlchemy or graph-building logic lives here.
"""

import uuid

from fastapi import APIRouter, Query, status

from app.api.deps import (
    CurrentUser,
    InterviewAgentProviderDep,
    InterviewExecutionServiceDep,
    InterviewPlannerServiceDep,
)
from app.models.enums import SessionStatus
from app.models.interview import InterviewSession, Question
from app.schemas.interview import (
    DifficultyPlanOut,
    InterviewPlanRequest,
    InterviewPlanResponse,
    InterviewSessionDetail,
    InterviewSessionSummary,
    PersonalizationOut,
    RoundPlanOut,
)
from app.schemas.interview_turn import (
    AbandonOut,
    AnswerResponseOut,
    AnswerSubmitRequest,
    CurrentTurnOut,
    EvaluationOut,
    NextOut,
    QuestionOut,
    ScoreOut,
    StartInterviewOut,
)

router = APIRouter(prefix="/interview-sessions", tags=["interviews"])


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_interview_plan(
    data: InterviewPlanRequest,
    current_user: CurrentUser,
    planner: InterviewPlannerServiceDep,
) -> InterviewSessionDetail:
    interview = await planner.create_plan(user=current_user, request=data)
    return InterviewSessionDetail.model_validate(interview)


@router.get("")
async def list_interviews(
    current_user: CurrentUser,
    planner: InterviewPlannerServiceDep,
    status_filter: SessionStatus | None = Query(default=None, alias="status"),
) -> list[InterviewSessionSummary]:
    interviews = await planner.list_for_user(
        current_user.id, status=status_filter.value if status_filter else None
    )
    return [InterviewSessionSummary.model_validate(i) for i in interviews]


@router.get("/{interview_id}")
async def get_interview(
    interview_id: uuid.UUID,
    current_user: CurrentUser,
    planner: InterviewPlannerServiceDep,
) -> InterviewSessionDetail:
    interview = await planner.get_owned(interview_id, current_user.id)
    return InterviewSessionDetail.model_validate(interview)


@router.get("/{interview_id}/plan")
async def get_interview_plan(
    interview_id: uuid.UUID,
    current_user: CurrentUser,
    planner: InterviewPlannerServiceDep,
) -> InterviewPlanResponse:
    interview = await planner.get_owned(interview_id, current_user.id)
    return _plan_response(interview)


def _plan_response(interview: InterviewSession) -> InterviewPlanResponse:
    snapshot = interview.plan_snapshot or {}
    difficulty = snapshot.get("difficulty", {})
    personalization = snapshot.get("personalization")
    return InterviewPlanResponse(
        interview_id=interview.id,
        status=interview.status,
        company=snapshot.get("company"),
        role=snapshot.get("role", {}),
        template=snapshot.get("template", {}),
        mode=interview.mode,
        rounds=[
            RoundPlanOut(
                round_type=r.round_type,
                sequence_no=r.sequence_no,
                weight=r.weight,
                planned_difficulty=r.planned_difficulty,
                is_required=bool(
                    next(
                        (
                            sr["is_required"]
                            for sr in snapshot.get("rounds", [])
                            if sr["sequence_no"] == r.sequence_no
                        ),
                        True,
                    )
                ),
            )
            for r in sorted(interview.rounds, key=lambda r: r.sequence_no)
        ],
        difficulty=DifficultyPlanOut(
            requested=interview.requested_difficulty,
            starting=interview.starting_difficulty,
            reasons=difficulty.get("reasons", []),
        ),
        personalization=(
            PersonalizationOut.model_validate(personalization) if personalization else None
        ),
        created_at=interview.created_at,
    )


# ============================================================================
# Execution (Module 5) — module §19: no internal reasoning/chain-of-thought
# ever crosses into these responses, only conclusions/scores/explanations.
# ============================================================================


@router.post("/{interview_id}/start")
async def start_interview(
    interview_id: uuid.UUID,
    current_user: CurrentUser,
    execution: InterviewExecutionServiceDep,
    provider: InterviewAgentProviderDep,
) -> StartInterviewOut:
    interview, question = await execution.start_interview(
        interview_id=interview_id, user_id=current_user.id, provider=provider
    )
    return StartInterviewOut(
        interview_id=interview.id,
        status=interview.status,
        current_round=question.round.round_type,
        current_difficulty=interview.current_difficulty,
        question=_question_out(question),
    )


@router.get("/{interview_id}/current-turn")
async def get_current_turn(
    interview_id: uuid.UUID,
    current_user: CurrentUser,
    execution: InterviewExecutionServiceDep,
) -> CurrentTurnOut:
    interview, question = await execution.get_current_turn(interview_id, current_user.id)
    current_round = None
    for round_ in sorted(interview.rounds, key=lambda r: r.sequence_no):
        if round_.sequence_no == interview.current_round_sequence:
            current_round = round_.round_type
            break
    return CurrentTurnOut(
        interview_id=interview.id,
        status=interview.status,
        current_round=current_round,
        current_difficulty=interview.current_difficulty,
        question=_question_out(question) if question else None,
        interview_complete=interview.status == SessionStatus.COMPLETED,
    )


@router.post("/{interview_id}/answers")
async def submit_answer(
    interview_id: uuid.UUID,
    data: AnswerSubmitRequest,
    current_user: CurrentUser,
    execution: InterviewExecutionServiceDep,
    provider: InterviewAgentProviderDep,
) -> AnswerResponseOut:
    interview, evaluation, previous_difficulty, next_question = await execution.submit_answer(
        interview_id=interview_id,
        user_id=current_user.id,
        question_id=data.question_id,
        answer_text=data.answer_text,
        provider=provider,
    )
    if next_question is not None:
        next_out = NextOut(type="question", question=_question_out(next_question))
    else:
        # No Module 7 report generator yet — report_id is intentionally
        # omitted rather than fabricated (deviation from API.md's sketch,
        # documented here the same way prior modules document their own).
        next_out = NextOut(type="session_complete")
    return AnswerResponseOut(
        interview_id=interview.id,
        status=interview.status,
        evaluation=_evaluation_out(evaluation),
        previous_difficulty=previous_difficulty,
        current_difficulty=interview.current_difficulty,
        next=next_out,
    )


@router.post("/{interview_id}/abandon")
async def abandon_interview(
    interview_id: uuid.UUID,
    current_user: CurrentUser,
    execution: InterviewExecutionServiceDep,
) -> AbandonOut:
    interview = await execution.abandon(interview_id, current_user.id)
    return AbandonOut(
        interview_id=interview.id, status=interview.status, completed_at=interview.completed_at
    )


def _question_out(question: Question) -> QuestionOut:
    # Built field-by-field rather than QuestionOut.model_validate(question)
    # — round_type isn't a column on Question itself (it lives on the
    # parent InterviewRound), and the caller already knows it from
    # whichever InterviewRound row it just fetched.
    round_type = question.round.round_type if question.round is not None else None
    return QuestionOut(
        id=question.id,
        question_text=question.question_text,
        topic=question.topic,
        difficulty=question.difficulty,
        round_type=round_type,
        parent_question_id=question.parent_question_id,
    )


def _evaluation_out(evaluation: dict) -> EvaluationOut:
    return EvaluationOut(
        technical=ScoreOut(**evaluation["technical"]),
        problem_solving=ScoreOut(**evaluation["problem_solving"]),
        communication=ScoreOut(**evaluation["communication"]),
        confidence=ScoreOut(**evaluation["confidence"]),
        difficulty_signal=evaluation["difficulty_signal"],
    )
