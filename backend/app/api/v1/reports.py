"""Report/Roadmap API — Module 7. New sub-resource endpoints: report
generation itself never happens here (decision #1) — this router only
ever reads what the background job already produced, or updates one
roadmap item's completion flag.

Thin per Architecture.md §4: parses the request, calls exactly one
ReportService method, shapes the response. No SQLAlchemy logic lives
here, and no ownership logic either — every ReportService method takes
`user_id` and does its own ownership-scoped query (mirrors
code_submissions.py's own convention).

No shared path prefix across these three routes (unlike code_submissions.py,
whose whole surface lives under one interview_id-scoped prefix) — full
paths are spelled out per route instead.
"""

import uuid

from fastapi import APIRouter

import app.jobs.report_generation  # noqa: F401 — import registers JOB_HANDLERS["generate_report"]
from app.api.deps import CurrentUser, ReportServiceDep
from app.models.report import InterviewReport, LearningRoadmap, RoadmapItem
from app.schemas.report import (
    ReportOut,
    RoadmapItemOut,
    RoadmapItemUpdateRequest,
    RoadmapOut,
    ScoreExplanationOut,
    StrongAreaOut,
    WeakAreaOut,
)

router = APIRouter(tags=["reports"])


@router.get("/interview-sessions/{interview_id}/report")
async def get_report(
    interview_id: uuid.UUID,
    current_user: CurrentUser,
    reports: ReportServiceDep,
) -> ReportOut:
    report = await reports.get_report_for_session(interview_id, current_user.id)
    return _report_out(report)


@router.get("/reports/{report_id}/roadmap")
async def get_roadmap(
    report_id: uuid.UUID,
    current_user: CurrentUser,
    reports: ReportServiceDep,
) -> RoadmapOut:
    roadmap = await reports.get_roadmap_for_report(report_id, current_user.id)
    return _roadmap_out(roadmap)


@router.patch("/roadmap-items/{item_id}")
async def update_roadmap_item(
    item_id: uuid.UUID,
    data: RoadmapItemUpdateRequest,
    current_user: CurrentUser,
    reports: ReportServiceDep,
) -> RoadmapItemOut:
    item = await reports.update_roadmap_item(
        item_id, current_user.id, is_completed=data.is_completed
    )
    return _roadmap_item_out(item)


def _report_out(report: InterviewReport) -> ReportOut:
    # section_scores/weak_areas/strong_areas/roadmap are all eager-loaded
    # by InterviewReportRepository (app/repositories/report.py's
    # _REPORT_LOAD_OPTIONS) for every code path this function is reached
    # from — never lazy-loaded here.
    sections = {
        s.section.value: ScoreExplanationOut(score=float(s.score), explanation=s.explanation)
        for s in report.section_scores
    }
    return ReportOut(
        id=report.id,
        overall=ScoreExplanationOut(
            score=float(report.overall_score), explanation=report.overall_explanation
        ),
        sections=sections,
        weak_areas=[
            WeakAreaOut(topic=w.topic, severity=w.severity, evidence=w.evidence_text)
            for w in report.weak_areas
        ],
        strong_areas=[
            StrongAreaOut(topic=s.topic, evidence=s.evidence_text) for s in report.strong_areas
        ],
        summary=report.summary_text,
    )


def _roadmap_out(roadmap: LearningRoadmap) -> RoadmapOut:
    return RoadmapOut(
        id=roadmap.id,
        generated_at=roadmap.generated_at,
        items=[_roadmap_item_out(i) for i in roadmap.items],
    )


def _roadmap_item_out(item: RoadmapItem) -> RoadmapItemOut:
    return RoadmapItemOut(
        id=item.id,
        topic=item.topic,
        resource_title=item.resource_title,
        resource_url=item.resource_url,
        resource_type=item.resource_type,
        priority=item.priority,
        sequence_no=item.sequence_no,
        is_completed=item.is_completed,
    )
