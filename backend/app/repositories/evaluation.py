"""Evaluation repository (Database.md §6). `app/models/evaluation.py` was
modeled ahead of time (Module 1 baseline); Module 5 is the first module to
actually write to it — CodingEvaluation remains untouched (Module 6).
"""

import uuid

from sqlalchemy import select

from app.models.evaluation import AnswerEvaluation
from app.models.interview import Answer, InterviewRound, Question
from app.repositories.base import BaseRepository


class AnswerEvaluationRepository(BaseRepository[AnswerEvaluation]):
    model = AnswerEvaluation

    async def get_by_answer_id(self, answer_id: uuid.UUID) -> AnswerEvaluation | None:
        stmt = select(AnswerEvaluation).where(AnswerEvaluation.answer_id == answer_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_session(self, session_id: uuid.UUID) -> list[AnswerEvaluation]:
        """Every evaluation across every round of this interview so far —
        the durable basis for InterviewState.interview_scores, rebuilt
        fresh each turn rather than carried forward from a checkpoint
        (module §4: Postgres is the source of truth).
        """
        stmt = (
            select(AnswerEvaluation)
            .join(Answer, AnswerEvaluation.answer_id == Answer.id)
            .join(Question, Answer.question_id == Question.id)
            .join(InterviewRound, Question.round_id == InterviewRound.id)
            .where(InterviewRound.session_id == session_id)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_session_with_round_id(
        self, session_id: uuid.UUID
    ) -> list[tuple[AnswerEvaluation, uuid.UUID]]:
        """Module 7 — same join as list_for_session above, but also
        returns each row's `InterviewRound.id` so ReportService can group
        scores by round (Database.md §7's overall_score needs a per-round
        composite before it can apply `interview_rounds.weight`).
        Added as a new method rather than changing list_for_session's
        return shape — that method already has a caller
        (InterviewState.interview_scores) that depends on its current
        flat-list shape.
        """
        stmt = (
            select(AnswerEvaluation, InterviewRound.id)
            .join(Answer, AnswerEvaluation.answer_id == Answer.id)
            .join(Question, Answer.question_id == Question.id)
            .join(InterviewRound, Question.round_id == InterviewRound.id)
            .where(InterviewRound.session_id == session_id)
        )
        result = await self._session.execute(stmt)
        return [(row[0], row[1]) for row in result.all()]
