"""Interview session (planning) API — API.md §4, Module 4.

Only planning endpoints live here (`POST`/`GET /interview-sessions`,
`GET /interview-sessions/{id}/plan`) — start/current-turn/answers/abandon
from API.md §4 are Module 5's (interview execution), out of scope for
this module (module §1, §11) and deliberately not implemented here.

Thin per Architecture.md §4: parses the request, calls exactly one
InterviewPlannerService method, shapes the response.
"""

import uuid

from fastapi import APIRouter, Query, status

from app.api.deps import CurrentUser, InterviewPlannerServiceDep
from app.models.enums import SessionStatus
from app.models.interview import InterviewSession
from app.schemas.interview import (
    DifficultyPlanOut,
    InterviewPlanRequest,
    InterviewPlanResponse,
    InterviewSessionDetail,
    InterviewSessionSummary,
    PersonalizationOut,
    RoundPlanOut,
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
