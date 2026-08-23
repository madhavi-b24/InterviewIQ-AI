"""ReportService — Module 7's post-session report/roadmap generation and
read/update use cases. Entirely separate from InterviewExecutionService's
turn-based graph flow (decision #2 — a post-session aggregation workflow,
never a LangGraph turn node; the same architectural split Module 6's
CodingRoundService already makes for Run/Submit, which also stays outside
the graph).

generate_report_for_session (called only by app/jobs/report_generation.py,
never by a request handler) is single-shot, not two-phase (unlike Module
6's Run/Submit): there's no user-facing "queued" state to protect ahead of
the LLM call, since SessionStatus.COMPLETED is already durably committed
by execution_service.py before this job even starts. So: compute every
score deterministically first (app/agents/policy.py — never Gemini), call
ReportGenerationProvider exactly once for narrative content, and only then
issue one atomic commit of the whole report graph (using the models'
existing `cascade="all, delete-orphan"` relationships — one `session.add`
inserts the report and every child row). A failure at any point before
that commit leaves nothing behind — no partial/orphan rows, no retry
logic (matches app/jobs/coding_execution.py's/resume_processing.py's
established "no retry, log and stop" pattern — the exception is left to
propagate out of this method; the job is where it's caught and logged).

Idempotency: InterviewReport.session_id is unique (Module 1 baseline) — a
pre-check returns the existing report early, and the commit is wrapped in
the same try/except IntegrityError -> rollback -> requery -> return
-existing pattern app/services/coding/coding_round_service.py's
create_submission already establishes (module §22).
"""

import uuid
from collections import defaultdict
from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.policy import (
    classify_weak_area_severity,
    compute_overall_score,
    compute_round_composite,
    compute_section_score,
)
from app.core.exceptions import NotFoundError
from app.core.logging import get_logger
from app.models.enums import ReportSection, ResourceType
from app.models.evaluation import AnswerEvaluation, CodingEvaluation
from app.models.report import (
    InterviewReport,
    LearningRoadmap,
    ReportSectionScore,
    ReportStrongArea,
    ReportWeakArea,
    RoadmapItem,
)
from app.repositories.coding import CodingEvaluationRepository
from app.repositories.evaluation import AnswerEvaluationRepository
from app.repositories.interview import InterviewSessionRepository
from app.repositories.report import InterviewReportRepository, RoadmapItemRepository
from app.services.interview.execution_context import build_execution_context
from app.services.report_generation.provider import AnswerEvidence, ReportGenerationProvider
from app.services.report_generation.schemas import ReportContentResult

logger = get_logger(__name__)


class ReportService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._interviews = InterviewSessionRepository(session)
        self._answer_evaluations = AnswerEvaluationRepository(session)
        self._coding_evaluations = CodingEvaluationRepository(session)
        self._reports = InterviewReportRepository(session)
        self._roadmap_items = RoadmapItemRepository(session)

    # --- Generation (called only by the background job) ------------------

    async def generate_report_for_session(
        self, session_id: uuid.UUID, *, user_id: uuid.UUID, provider: ReportGenerationProvider
    ) -> InterviewReport | None:
        existing = await self._reports.get_by_session_id(session_id)
        if existing is not None:
            logger.info("report.generate.idempotent_replay", session_id=str(session_id))
            return existing

        interview = await self._interviews.get_owned(session_id, user_id)
        if interview is None:
            raise NotFoundError("interview not found", code="INTERVIEW_NOT_FOUND")

        round_weight_by_id = {r.id: float(r.weight) for r in interview.rounds}
        round_type_by_id = {r.id: r.round_type.value for r in interview.rounds}

        answer_evals = await self._answer_evaluations.list_for_session_with_round_id(session_id)
        coding_evals = await self._coding_evaluations.list_for_session_with_round_id(session_id)

        section_scores = self._compute_section_scores(answer_evals, coding_evals)
        overall_score = self._compute_overall_score(answer_evals, coding_evals, round_weight_by_id)
        evidence = self._build_evidence(answer_evals, coding_evals, round_type_by_id)

        context = build_execution_context(interview)
        content = await provider.generate(
            role_title=context.role_title,
            company_name=context.company_name,
            section_scores=section_scores,
            overall_score=overall_score,
            evidence=evidence,
        )

        report = self._build_report(session_id, section_scores, overall_score, content)

        try:
            await self._reports.add(report)
            await self._session.commit()
        except IntegrityError:
            await self._session.rollback()
            # Two concurrent triggers for the same session raced past the
            # pre-check above — session_id's unique constraint is the real
            # backstop (module §22), same shape as
            # coding_round_service.py's final-submission race handling.
            existing = await self._reports.get_by_session_id(session_id)
            if existing is not None:
                logger.warning("report.generate.race_detected", session_id=str(session_id))
                return existing
            raise
        logger.info(
            "report.generate.completed", session_id=str(session_id), report_id=str(report.id)
        )
        return report

    @staticmethod
    def _compute_section_scores(
        answer_evals: list[tuple[AnswerEvaluation, uuid.UUID]],
        coding_evals: list[tuple[CodingEvaluation, uuid.UUID]],
    ) -> dict[str, float]:
        dimension_scores: dict[str, list[float]] = defaultdict(list)
        for ae, _round_id in answer_evals:
            dimension_scores["technical"].append(float(ae.technical_score))
            dimension_scores["problem_solving"].append(float(ae.problem_solving_score))
            dimension_scores["communication"].append(float(ae.communication_score))
            dimension_scores["confidence"].append(float(ae.confidence_score))
        for ce, _round_id in coding_evals:
            dimension_scores["coding"].append(float(ce.overall_code_score))
        return {
            name: compute_section_score(scores)
            for name, scores in dimension_scores.items()
            if scores
        }

    @staticmethod
    def _compute_overall_score(
        answer_evals: list[tuple[AnswerEvaluation, uuid.UUID]],
        coding_evals: list[tuple[CodingEvaluation, uuid.UUID]],
        round_weight_by_id: dict[uuid.UUID, float],
    ) -> float:
        round_scores: dict[uuid.UUID, list[float]] = defaultdict(list)
        for ae, round_id in answer_evals:
            round_scores[round_id].extend(
                [
                    float(ae.technical_score),
                    float(ae.problem_solving_score),
                    float(ae.communication_score),
                    float(ae.confidence_score),
                ]
            )
        for ce, round_id in coding_evals:
            round_scores[round_id].append(float(ce.overall_code_score))

        round_composites = [
            (compute_round_composite(scores), round_weight_by_id.get(round_id, 0.0))
            for round_id, scores in round_scores.items()
            if scores
        ]
        return compute_overall_score(round_composites)

    @staticmethod
    def _build_evidence(
        answer_evals: list[tuple[AnswerEvaluation, uuid.UUID]],
        coding_evals: list[tuple[CodingEvaluation, uuid.UUID]],
        round_type_by_id: dict[uuid.UUID, str],
    ) -> list[AnswerEvidence]:
        evidence: list[AnswerEvidence] = []
        for ae, round_id in answer_evals:
            round_type = round_type_by_id.get(round_id, "unknown")
            evidence.extend(
                [
                    AnswerEvidence(
                        round_type=round_type,
                        dimension="technical",
                        score=float(ae.technical_score),
                        explanation=ae.technical_explanation,
                    ),
                    AnswerEvidence(
                        round_type=round_type,
                        dimension="problem_solving",
                        score=float(ae.problem_solving_score),
                        explanation=ae.problem_solving_explanation,
                    ),
                    AnswerEvidence(
                        round_type=round_type,
                        dimension="communication",
                        score=float(ae.communication_score),
                        explanation=ae.communication_explanation,
                    ),
                    AnswerEvidence(
                        round_type=round_type,
                        dimension="confidence",
                        score=float(ae.confidence_score),
                        explanation=ae.confidence_explanation,
                    ),
                ]
            )
        for ce, round_id in coding_evals:
            round_type = round_type_by_id.get(round_id, "unknown")
            evidence.extend(
                [
                    AnswerEvidence(
                        round_type=round_type,
                        dimension="coding_correctness",
                        score=float(ce.correctness_score),
                        explanation=ce.correctness_explanation,
                    ),
                    AnswerEvidence(
                        round_type=round_type,
                        dimension="coding_readability",
                        score=float(ce.readability_score),
                        explanation=ce.readability_explanation,
                    ),
                    AnswerEvidence(
                        round_type=round_type,
                        dimension="coding_optimization",
                        score=float(ce.optimization_score),
                        explanation=ce.optimization_explanation,
                    ),
                    AnswerEvidence(
                        round_type=round_type,
                        dimension="coding_edge_case",
                        score=float(ce.edge_case_score),
                        explanation=ce.edge_case_explanation,
                    ),
                ]
            )
        return evidence

    @staticmethod
    def _build_report(
        session_id: uuid.UUID,
        section_scores: dict[str, float],
        overall_score: float,
        content: ReportContentResult,
    ) -> InterviewReport:
        now = datetime.now(UTC)
        explanation_by_section = {
            "technical": content.technical_explanation,
            "problem_solving": content.problem_solving_explanation,
            "communication": content.communication_explanation,
            "confidence": content.confidence_explanation,
            "coding": content.coding_explanation,
        }

        report = InterviewReport(
            session_id=session_id,
            overall_score=overall_score,
            overall_explanation=content.overall_explanation,
            summary_text=content.summary_text,
            generated_at=now,
        )
        report.section_scores = [
            ReportSectionScore(
                section=ReportSection(name),
                score=score,
                # Defensive fallback only — every section present in
                # section_scores was also given to the provider, so the
                # matching explanation should always be set; this guards
                # against a malformed/incomplete Gemini response rather
                # than expecting one in normal operation.
                explanation=explanation_by_section.get(name) or "No explanation provided.",
            )
            for name, score in section_scores.items()
        ]
        report.weak_areas = [
            ReportWeakArea(
                topic=wa.topic,
                severity=classify_weak_area_severity(section_scores[wa.section]),
                evidence_text=wa.evidence_text,
                section=ReportSection(wa.section),
            )
            for wa in content.weak_areas
            if wa.section in section_scores
        ]
        report.strong_areas = [
            ReportStrongArea(
                topic=sa.topic,
                evidence_text=sa.evidence_text,
                section=ReportSection(sa.section) if sa.section in section_scores else None,
            )
            for sa in content.strong_areas
        ]

        roadmap_items_sorted = sorted(content.roadmap_items, key=lambda item: item.priority)
        roadmap = LearningRoadmap(generated_at=now)
        roadmap.items = [
            RoadmapItem(
                topic=item.topic,
                resource_title=item.resource_title,
                resource_url=item.resource_url,
                resource_type=ResourceType(item.resource_type),
                priority=item.priority,
                sequence_no=i + 1,
                is_completed=False,
            )
            for i, item in enumerate(roadmap_items_sorted)
        ]
        report.roadmap = roadmap
        return report

    # --- Reads / updates (API layer) --------------------------------------

    async def get_report_for_session(
        self, session_id: uuid.UUID, user_id: uuid.UUID
    ) -> InterviewReport:
        report = await self._reports.get_owned_by_session(session_id, user_id)
        if report is None:
            interview = await self._interviews.get_owned(session_id, user_id)
            if interview is None:
                raise NotFoundError("interview not found", code="INTERVIEW_NOT_FOUND")
            # Distinguishes "you can't see this" from "report generation
            # hasn't finished (or previously failed) yet" — no synchronous
            # fallback generation here (decision #1: report generation
            # only ever happens in the background job, never inline in a
            # request handler).
            raise NotFoundError(
                "the report for this session has not been generated yet",
                code="REPORT_NOT_YET_AVAILABLE",
            )
        return report

    async def get_roadmap_for_report(
        self, report_id: uuid.UUID, user_id: uuid.UUID
    ) -> LearningRoadmap:
        roadmap = await self._reports.get_owned_roadmap_by_report_id(report_id, user_id)
        if roadmap is None:
            raise NotFoundError("roadmap not found", code="ROADMAP_NOT_FOUND")
        return roadmap

    async def update_roadmap_item(
        self, item_id: uuid.UUID, user_id: uuid.UUID, *, is_completed: bool
    ) -> RoadmapItem:
        item = await self._roadmap_items.get_owned_by_id(item_id, user_id)
        if item is None:
            raise NotFoundError("roadmap item not found", code="ROADMAP_ITEM_NOT_FOUND")
        item.is_completed = is_completed
        await self._session.commit()
        return item
