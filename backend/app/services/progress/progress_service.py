"""ProgressService — Module 8's post-report progress-aggregation use case.

`record_session_progress` is the write path (decision: no background job
of its own — see module docstring above and app/jobs/report_generation.py
for why). Called exactly once per generated report, right after
ReportService.generate_report_for_session commits, in the *same* session.
`report`'s relationship attributes (`section_scores`/`weak_areas`/
`strong_areas`) are the in-memory Python objects ReportService built —
safely readable post-commit because get_session_factory() sets
expire_on_commit=False (app/db/session.py); this method still captures
every value it needs as plain locals before any retry/rollback below, the
same discipline app/services/coding/coding_round_service.py's own module
docstring establishes (a rollback expires the whole session, and
re-reading an attribute off an expired ORM object triggers an implicit
refresh that's unsafe under the async engine — MissingGreenlet).

Idempotency: every write here is read-existing-row-then-upsert, never a
blind insert — re-running for the same session recomputes the same
correct state rather than duplicating anything. `skill_progress`/
`company_readiness`/`user_progress_snapshots` each have their own unique
constraint (Module 1 baseline) as the real concurrency backstop; a race
is handled by rollback-and-retry-once (module §22's established pattern),
not a bespoke per-table merge — every write here is cheap, deterministic
recomputation, so a clean retry always converges to the same result.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.policy import classify_score_trend
from app.core.logging import get_logger
from app.models.enums import ProgressTrend
from app.models.interview import InterviewSession
from app.models.progress import CompanyReadiness, SkillProgress, UserProgressSnapshot
from app.models.report import InterviewReport
from app.repositories.progress import (
    CompanyReadinessRepository,
    InterviewHistoryRepository,
    SkillProgressRepository,
    UserProgressSnapshotRepository,
)
from app.services.resume.skill_normalization import normalize_skill

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class DashboardOverview:
    interviews_completed: int
    avg_overall_score: float
    trend: ProgressTrend


class ProgressService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._snapshots = UserProgressSnapshotRepository(session)
        self._company_readiness = CompanyReadinessRepository(session)
        self._skills = SkillProgressRepository(session)
        self._history = InterviewHistoryRepository(session)

    # --- Write path (called only from app/jobs/report_generation.py) -----

    async def record_session_progress(self, report: InterviewReport, *, user_id: uuid.UUID) -> None:
        interview = await self._session.get(InterviewSession, report.session_id)
        if interview is None:
            logger.warning("progress.record.session_missing", session_id=str(report.session_id))
            return

        # Captured as plain values now — see module docstring on why this
        # must happen before any rollback below.
        session_id = report.session_id
        company_id = interview.company_id
        overall_score = float(report.overall_score)
        section_score_by_name = {s.section.value: float(s.score) for s in report.section_scores}
        # weak_areas first, strong_areas second — deliberate tie-break if a
        # topic somehow appears in both (structurally unlikely, never
        # enforced by the LLM schema): the earlier entry wins, deterministic
        # regardless of input order.
        topic_sections: list[tuple[str, str]] = [
            (wa.topic, wa.section.value) for wa in report.weak_areas if wa.section is not None
        ] + [(sa.topic, sa.section.value) for sa in report.strong_areas if sa.section is not None]

        for attempt in (1, 2):
            try:
                await self._upsert_snapshot(user_id)
                if company_id is not None:
                    await self._upsert_company_readiness(
                        user_id, company_id, session_id, overall_score
                    )
                await self._upsert_skill_progress(user_id, topic_sections, section_score_by_name)
                await self._session.commit()
                return
            except IntegrityError:
                await self._session.rollback()
                if attempt == 2:
                    logger.error("progress.record.failed_after_retry", user_id=str(user_id))
                    raise
                logger.warning("progress.record.race_detected_retrying", user_id=str(user_id))

    async def _upsert_snapshot(self, user_id: uuid.UUID) -> None:
        interviews_completed, avg_overall_score = await self._snapshots.count_and_average_for_user(
            user_id
        )
        today = date.today()
        existing = await self._snapshots.get_by_user_and_date(user_id, today)
        if existing is not None:
            existing.interviews_completed = interviews_completed
            existing.avg_overall_score = avg_overall_score
        else:
            snapshot = UserProgressSnapshot(
                user_id=user_id,
                snapshot_date=today,
                interviews_completed=interviews_completed,
                avg_overall_score=avg_overall_score,
            )
            await self._snapshots.add(snapshot)

    async def _upsert_company_readiness(
        self, user_id: uuid.UUID, company_id: uuid.UUID, session_id: uuid.UUID, overall_score: float
    ) -> None:
        now = datetime.now(UTC)
        existing = await self._company_readiness.get_by_user_and_company(user_id, company_id)
        if existing is not None:
            existing.readiness_score = overall_score
            existing.last_interview_session_id = session_id
            existing.updated_at = now
        else:
            row = CompanyReadiness(
                user_id=user_id,
                company_id=company_id,
                readiness_score=overall_score,
                last_interview_session_id=session_id,
                updated_at=now,
            )
            await self._company_readiness.add(row)

    async def _upsert_skill_progress(
        self,
        user_id: uuid.UUID,
        topic_sections: list[tuple[str, str]],
        section_score_by_name: dict[str, float],
    ) -> None:
        now = datetime.now(UTC)
        seen: set[str] = set()
        for topic, section in topic_sections:
            score = section_score_by_name.get(section)
            if score is None:
                continue
            skill_name = normalize_skill(topic).canonical
            if skill_name in seen:
                continue
            seen.add(skill_name)

            existing = await self._skills.get_by_user_and_skill(user_id, skill_name)
            if existing is not None:
                delta = score - float(existing.proficiency_score)
                existing.proficiency_score = score
                existing.trend = classify_score_trend(delta)
                existing.last_assessed_at = now
                existing.updated_at = now
            else:
                row = SkillProgress(
                    user_id=user_id,
                    skill_name=skill_name,
                    proficiency_score=score,
                    trend=ProgressTrend.STABLE,
                    last_assessed_at=now,
                    updated_at=now,
                )
                await self._skills.add(row)

    # --- Reads (API layer) -------------------------------------------------

    async def get_overview(self, user_id: uuid.UUID) -> DashboardOverview:
        snapshots = await self._snapshots.list_for_user(user_id)
        if not snapshots:
            return DashboardOverview(
                interviews_completed=0, avg_overall_score=0.0, trend=ProgressTrend.STABLE
            )
        latest = snapshots[-1]
        if len(snapshots) >= 2:
            previous = snapshots[-2]
            delta = float(latest.avg_overall_score) - float(previous.avg_overall_score)
            trend = classify_score_trend(delta)
        else:
            trend = ProgressTrend.STABLE
        return DashboardOverview(
            interviews_completed=latest.interviews_completed,
            avg_overall_score=float(latest.avg_overall_score),
            trend=trend,
        )

    async def list_skills(self, user_id: uuid.UUID) -> list[SkillProgress]:
        return await self._skills.list_for_user(user_id)

    async def list_company_readiness(
        self, user_id: uuid.UUID
    ) -> list[tuple[CompanyReadiness, str]]:
        return await self._company_readiness.list_for_user_with_company_name(user_id)

    async def list_history(
        self, user_id: uuid.UUID, *, limit: int, offset: int
    ) -> tuple[list[tuple[InterviewSession, InterviewReport | None]], int]:
        return await self._history.list_for_user(user_id, limit=limit, offset=offset)
