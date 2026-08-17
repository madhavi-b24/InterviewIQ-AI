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
