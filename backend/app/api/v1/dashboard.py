"""Dashboard API — Module 8. Four read-only endpoints, API.md §7. No
report/progress generation happens here — that's ProgressService.
record_session_progress, called only from app/jobs/report_generation.py
(Module 8's one approved Module 7 integration point). This router only
ever reads what that already produced.

Thin per Architecture.md §4: parses the request, calls exactly one
ProgressService method, shapes the response. No SQLAlchemy logic here,
and no ownership logic either — every ProgressService method takes
current_user.id directly and scopes its own query, mirroring
code_submissions.py's/reports.py's own convention.
"""

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, ProgressServiceDep
from app.models.interview import InterviewSession
from app.models.progress import CompanyReadiness, SkillProgress
from app.models.report import InterviewReport
from app.schemas.progress import (
    CompanyReadinessOut,
    DashboardOverviewOut,
    HistoryItemOut,
    HistoryReportSummaryOut,
    PaginatedHistoryOut,
    SkillProgressOut,
)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

# Smallest reasonable scheme — no other endpoint in this project paginates
# yet, so there's no existing convention to extend; plain limit/offset
# with a sane default and a hard ceiling (never an unbounded query).
_DEFAULT_HISTORY_LIMIT = 20
_MAX_HISTORY_LIMIT = 100


@router.get("/overview")
async def get_overview(
    current_user: CurrentUser, progress: ProgressServiceDep
) -> DashboardOverviewOut:
    overview = await progress.get_overview(current_user.id)
    return DashboardOverviewOut(
        interviews_completed=overview.interviews_completed,
        avg_overall_score=overview.avg_overall_score,
        trend=overview.trend,
    )


@router.get("/skills")
async def get_skills(
    current_user: CurrentUser, progress: ProgressServiceDep
) -> list[SkillProgressOut]:
    skills = await progress.list_skills(current_user.id)
    return [_skill_out(s) for s in skills]


@router.get("/company-readiness")
async def get_company_readiness(
    current_user: CurrentUser, progress: ProgressServiceDep
) -> list[CompanyReadinessOut]:
    rows = await progress.list_company_readiness(current_user.id)
    return [_company_readiness_out(readiness, name) for readiness, name in rows]


@router.get("/history")
async def get_history(
    current_user: CurrentUser,
    progress: ProgressServiceDep,
    limit: int = Query(default=_DEFAULT_HISTORY_LIMIT, ge=1, le=_MAX_HISTORY_LIMIT),
    offset: int = Query(default=0, ge=0),
) -> PaginatedHistoryOut:
    rows, total = await progress.list_history(current_user.id, limit=limit, offset=offset)
    return PaginatedHistoryOut(
        items=[_history_item_out(session, report) for session, report in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


def _skill_out(skill: SkillProgress) -> SkillProgressOut:
    return SkillProgressOut(
        skill_name=skill.skill_name,
        proficiency_score=float(skill.proficiency_score),
        trend=skill.trend,
        last_assessed_at=skill.last_assessed_at,
    )


def _company_readiness_out(readiness: CompanyReadiness, company_name: str) -> CompanyReadinessOut:
    return CompanyReadinessOut(
        company_id=readiness.company_id,
        company_name=company_name,
        readiness_score=float(readiness.readiness_score),
        last_interview_session_id=readiness.last_interview_session_id,
        updated_at=readiness.updated_at,
    )


def _history_item_out(session: InterviewSession, report: InterviewReport | None) -> HistoryItemOut:
    return HistoryItemOut(
        session_id=session.id,
        status=session.status,
        created_at=session.created_at,
        completed_at=session.completed_at,
        report=(
            HistoryReportSummaryOut(
                id=report.id,
                overall_score=float(report.overall_score),
                generated_at=report.generated_at,
            )
            if report is not None
            else None
        ),
    )
