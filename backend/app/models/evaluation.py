"""Evaluation domain — Database.md §6.

Every score column is paired with a `..._explanation` column — no bare
number is ever stored, per the project's scoring standard.
"""

import uuid

from sqlalchemy import ForeignKey, Numeric, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin
from app.models.enums import DifficultySignal, pg_enum


class AnswerEvaluation(Base, UUIDPrimaryKeyMixin, CreatedAtMixin):
    """Produced by the Evaluation Agent (technical, problem_solving) and the
    Communication Agent (communication, confidence) for every answer.
    """

    __tablename__ = "answer_evaluations"

    answer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("answers.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    technical_score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    technical_explanation: Mapped[str] = mapped_column(Text, nullable=False)
    problem_solving_score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    problem_solving_explanation: Mapped[str] = mapped_column(Text, nullable=False)
    communication_score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    communication_explanation: Mapped[str] = mapped_column(Text, nullable=False)
    confidence_score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    confidence_explanation: Mapped[str] = mapped_column(Text, nullable=False)
    difficulty_signal: Mapped[DifficultySignal] = mapped_column(
        pg_enum(DifficultySignal, name="answer_evaluations_difficulty_signal_enum"), nullable=False
    )


class CodingEvaluation(Base, UUIDPrimaryKeyMixin, CreatedAtMixin):
    """Produced by the Evaluation Agent from the final code_submission only.
    correctness_score is computed from code_submission_test_results — see
    Architecture.md §5.4 — not LLM-guessed. readability/optimization are
    the only LLM-judged numbers here.
    """

    __tablename__ = "coding_evaluations"

    code_submission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("code_submissions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    correctness_score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    correctness_explanation: Mapped[str] = mapped_column(Text, nullable=False)
    time_complexity: Mapped[str | None] = mapped_column(Text, nullable=True)
    space_complexity: Mapped[str | None] = mapped_column(Text, nullable=True)
    readability_score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    readability_explanation: Mapped[str] = mapped_column(Text, nullable=False)
    optimization_score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    optimization_explanation: Mapped[str] = mapped_column(Text, nullable=False)
