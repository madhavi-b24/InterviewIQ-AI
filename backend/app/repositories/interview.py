"""Interview execution repositories (Database.md §5, Module 4 — planning
only; Module 5 — execution: InterviewRound/Question/Answer plus the
concurrency-lock read on InterviewSession).

Every read method takes `user_id` and filters by it in the query itself
where the row is user-owned — same ownership-enforcement pattern as
ResumeRepository (module §13): a cross-user interview id resolves as "not
found" at the query level, never as "found, then rejected in Python".
Question/Answer/round rows are children of an already-ownership-checked
InterviewSession, so their own repository methods take a round/session id
the caller has already verified ownership of, rather than re-deriving
ownership per child row.
"""

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.enums import RoundStatus
from app.models.interview import (
    Answer,
    InterviewRound,
    InterviewSession,
    Question,
    QuestionTestCase,
)
from app.repositories.base import BaseRepository


class InterviewSessionRepository(BaseRepository[InterviewSession]):
    model = InterviewSession

    async def get_owned(self, session_id: uuid.UUID, user_id: uuid.UUID) -> InterviewSession | None:
        stmt = (
            select(InterviewSession)
            .where(InterviewSession.id == session_id, InterviewSession.user_id == user_id)
            .options(selectinload(InterviewSession.rounds))
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_owned_for_update(
        self, session_id: uuid.UUID, user_id: uuid.UUID
    ) -> InterviewSession | None:
        """Module 5 — `SELECT ... FOR UPDATE` on the session row, held for
        the duration of one turn's transaction. Serializes concurrent
        submissions for the same session (double-click / retry-storm
        protection, module §22) — the row lock is the concurrency
        boundary; `rounds` is still read via the normal unlocked
        selectinload since nothing outside this same locked flow ever
        writes to a session's rounds during execution.
        """
        stmt = (
            select(InterviewSession)
            .where(InterviewSession.id == session_id, InterviewSession.user_id == user_id)
            .options(selectinload(InterviewSession.rounds))
            .with_for_update(of=InterviewSession)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_owned(
        self, user_id: uuid.UUID, *, status: str | None = None
    ) -> list[InterviewSession]:
        stmt = select(InterviewSession).where(InterviewSession.user_id == user_id)
        if status is not None:
            stmt = stmt.where(InterviewSession.status == status)
        stmt = stmt.order_by(InterviewSession.created_at.desc())
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


class InterviewRoundRepository(BaseRepository[InterviewRound]):
    model = InterviewRound

    async def get_by_sequence(
        self, session_id: uuid.UUID, sequence_no: int
    ) -> InterviewRound | None:
        stmt = select(InterviewRound).where(
            InterviewRound.session_id == session_id, InterviewRound.sequence_no == sequence_no
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def mark_status(
        self,
        round_: InterviewRound,
        status: RoundStatus,
        *,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
    ) -> InterviewRound:
        round_.status = status
        if started_at is not None:
            round_.started_at = started_at
        if completed_at is not None:
            round_.completed_at = completed_at
        await self._session.flush()
        return round_


class QuestionRepository(BaseRepository[Question]):
    model = Question

    async def list_for_round(self, round_id: uuid.UUID) -> list[Question]:
        stmt = select(Question).where(Question.round_id == round_id).order_by(Question.asked_at)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_with_round(self, question_id: uuid.UUID) -> Question | None:
        """Eager-loads `round` and `test_cases` explicitly — never relies
        on SQLAlchemy's lazy-load identity-map optimization for a
        relationship access being safe in an async session (module §5 API
        responses read `question.round.round_type`; module §6's coding
        endpoints read `question.test_cases` to shape a CodingProblemOut —
        empty and harmless to eager-load for every non-coding question).
        """
        stmt = (
            select(Question)
            .where(Question.id == question_id)
            .options(selectinload(Question.round), selectinload(Question.test_cases))
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_coding_problem_ids_for_session(self, session_id: uuid.UUID) -> list[uuid.UUID]:
        """Module 6 — every catalog problem id already used by a coding
        question anywhere in this interview (joins through
        InterviewRound, since Question has no direct session_id column).
        Feeds `coding_problem_history` in graph state so
        select_coding_problem avoids repeating a problem across multiple
        coding rounds in the same plan (app/agents/policy.py).
        """
        stmt = (
            select(Question.coding_problem_id)
            .join(InterviewRound, Question.round_id == InterviewRound.id)
            .where(
                InterviewRound.session_id == session_id,
                Question.coding_problem_id.isnot(None),
            )
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


class QuestionTestCaseRepository(BaseRepository[QuestionTestCase]):
    """Module 6 — the LIVE (snapshotted) test cases attached to a coding
    Question, distinct from CodingProblemTestCase (the catalog's own,
    mutable copy — app/repositories/coding.py). Never exposed via any API
    response for non-sample rows (module §8) — callers of `list_for_question`
    are the sandbox-execution path and the (ownership-checked) sample-only
    schema mapper, never a raw passthrough.
    """

    model = QuestionTestCase

    async def list_for_question(self, question_id: uuid.UUID) -> list[QuestionTestCase]:
        stmt = (
            select(QuestionTestCase)
            .where(QuestionTestCase.question_id == question_id)
            .order_by(QuestionTestCase.sequence_no)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


class AnswerRepository(BaseRepository[Answer]):
    model = Answer

    async def get_by_question_id(self, question_id: uuid.UUID) -> Answer | None:
        stmt = select(Answer).where(Answer.question_id == question_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_questions(self, question_ids: list[uuid.UUID]) -> list[Answer]:
        if not question_ids:
            return []
        stmt = select(Answer).where(Answer.question_id.in_(question_ids))
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
