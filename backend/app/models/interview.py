"""Interview execution domain — Database.md §5."""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin
from app.models.enums import (
    CodeExecutionStatus,
    DifficultyLevel,
    InterviewMode,
    QuestionSource,
    QuestionType,
    RequestedDifficulty,
    RoundStatus,
    RoundType,
    SessionStatus,
    pg_enum,
)


class InterviewSession(Base, UUIDPrimaryKeyMixin, CreatedAtMixin):
    __tablename__ = "interview_sessions"
    __table_args__ = (Index("ix_interview_sessions_user_status", "user_id", "status"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    # Module 4 — relaxed to nullable: a generic (non-resume-discussion) mode
    # may be planned with no resume at all (module §8). Pins the *exact*
    # resume row/version used — Module 3 resume rows are never mutated after
    # parsed_status=done (only is_active toggles), so this FK alone is
    # sufficient for reproducibility; no separate "resume version" column is
    # needed.
    resume_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("resumes.id", ondelete="RESTRICT"), nullable=True
    )
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="SET NULL"), nullable=True
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roles.id", ondelete="RESTRICT"), nullable=False
    )
    template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("interview_templates.id", ondelete="RESTRICT"),
        nullable=False,
    )
    status: Mapped[SessionStatus] = mapped_column(
        pg_enum(SessionStatus, name="interview_sessions_status_enum"),
        nullable=False,
        default=SessionStatus.NOT_STARTED,
    )
    current_round_sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Module 4 — the *dynamic* difficulty. Set equal to starting_difficulty
    # at plan time; Module 5's Difficulty Agent is the only thing that will
    # ever change it afterward. Never confuse this with starting_difficulty
    # below (module §7's explicit instruction).
    current_difficulty: Mapped[DifficultyLevel] = mapped_column(
        pg_enum(DifficultyLevel, name="interview_sessions_current_difficulty_enum"),
        nullable=False,
    )
    # Module 4 — what the candidate actually asked for (an explicit level,
    # or AUTO). Persisted verbatim, independent of what it resolved to.
    requested_difficulty: Mapped[RequestedDifficulty] = mapped_column(
        pg_enum(RequestedDifficulty, name="interview_sessions_requested_difficulty_enum"),
        nullable=False,
        default=RequestedDifficulty.AUTO,
    )
    # Module 4 — the resolved starting difficulty at plan time: requested_difficulty
    # as-is if explicit, or the deterministic AUTO resolution (module §7) if
    # requested_difficulty=AUTO. Immutable after creation — an audit-safe
    # snapshot distinct from current_difficulty, which Module 5 will mutate.
    starting_difficulty: Mapped[DifficultyLevel] = mapped_column(
        pg_enum(DifficultyLevel, name="interview_sessions_starting_difficulty_enum"),
        nullable=False,
    )
    # Module 4 — which candidate-facing mode this session was planned as.
    # Inherited from (and, if the request specified one, validated against)
    # interview_templates.mode at plan time.
    mode: Mapped[InterviewMode] = mapped_column(
        pg_enum(InterviewMode, name="interview_sessions_mode_enum"),
        nullable=False,
        default=InterviewMode.FULL_MOCK,
    )
    # Module 4 — the immutable plan snapshot (module §9): denormalized
    # company/role/template/round labels + the resume-derived personalization
    # context (skills/focus areas/evidence, never raw resume text or PII)
    # captured at plan time. Round order/weights/planned-difficulty
    # themselves stay normalized in interview_rounds (queryable, matches
    # Database.md's existing snapshot pattern there) — this column only
    # carries what would otherwise require re-joining mutable catalog/resume
    # tables to redisplay a plan that must never silently change.
    plan_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    langgraph_thread_id: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Module 5 — explicit pointer to the pending turn's question. Nullable:
    # None before /start, and again once status is completed/abandoned.
    # Lets GET /current-turn and resume-after-interruption be a single
    # indexed read instead of a derived "question with no answer yet"
    # query — the recoverability Postgres, not the graph state, provides
    # (see app/agents/state.py's module docstring).
    current_question_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("questions.id", ondelete="SET NULL"), nullable=True
    )

    rounds: Mapped[list["InterviewRound"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="InterviewRound.sequence_no",
    )


class InterviewRound(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "interview_rounds"
    __table_args__ = (UniqueConstraint("session_id", "sequence_no"),)

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("interview_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    template_round_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("template_rounds.id", ondelete="RESTRICT"), nullable=False
    )
    round_type: Mapped[RoundType] = mapped_column(
        pg_enum(RoundType, name="interview_rounds_round_type_enum"), nullable=False
    )
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False)
    weight: Mapped[float] = mapped_column(Numeric(4, 2), nullable=False)
    planned_difficulty: Mapped[DifficultyLevel] = mapped_column(
        pg_enum(DifficultyLevel, name="interview_rounds_planned_difficulty_enum"), nullable=False
    )
    status: Mapped[RoundStatus] = mapped_column(
        pg_enum(RoundStatus, name="interview_rounds_status_enum"),
        nullable=False,
        default=RoundStatus.PENDING,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    session: Mapped["InterviewSession"] = relationship(back_populates="rounds")
    questions: Mapped[list["Question"]] = relationship(
        back_populates="round", cascade="all, delete-orphan"
    )


class Question(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "questions"

    round_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("interview_rounds.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    topic: Mapped[str] = mapped_column(Text, nullable=False)
    difficulty: Mapped[DifficultyLevel] = mapped_column(
        pg_enum(DifficultyLevel, name="questions_difficulty_enum"), nullable=False
    )
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    question_type: Mapped[QuestionType] = mapped_column(
        pg_enum(QuestionType, name="questions_question_type_enum"), nullable=False
    )
    reference_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[QuestionSource] = mapped_column(
        pg_enum(QuestionSource, name="questions_source_enum"), nullable=False
    )
    vector_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    asked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Module 5 — self-referential: set when this question is a follow-up to
    # another question in the same round (module §8: "persist follow-up
    # relationships"). None for a fresh, round-opening question.
    parent_question_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("questions.id", ondelete="SET NULL"), nullable=True
    )

    round: Mapped["InterviewRound"] = relationship(back_populates="questions")
    test_cases: Mapped[list["QuestionTestCase"]] = relationship(
        back_populates="question",
        cascade="all, delete-orphan",
        order_by="QuestionTestCase.sequence_no",
    )
    answer: Mapped["Answer | None"] = relationship(back_populates="question", uselist=False)


class QuestionTestCase(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "question_test_cases"
    __table_args__ = (UniqueConstraint("question_id", "sequence_no"),)

    question_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("questions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    input: Mapped[str] = mapped_column(Text, nullable=False)
    expected_output: Mapped[str] = mapped_column(Text, nullable=False)
    is_sample: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    weight: Mapped[float] = mapped_column(Numeric(4, 2), nullable=False, default=1.00)
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False)

    question: Mapped["Question"] = relationship(back_populates="test_cases")


class Answer(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "answers"

    question_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("questions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    answer_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_time_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    question: Mapped["Question"] = relationship(back_populates="answer")
    code_submissions: Mapped[list["CodeSubmission"]] = relationship(
        back_populates="answer", cascade="all, delete-orphan", order_by="CodeSubmission.attempt_no"
    )


class CodeSubmission(Base, UUIDPrimaryKeyMixin, CreatedAtMixin):
    """One row per attempt. See Database.md §5 — only `is_final=True` is graded."""

    __tablename__ = "code_submissions"
    __table_args__ = (
        UniqueConstraint("answer_id", "attempt_no"),
        Index(
            "ux_code_submissions_final",
            "answer_id",
            unique=True,
            postgresql_where=text("is_final"),
        ),
    )

    answer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("answers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    attempt_no: Mapped[int] = mapped_column(Integer, nullable=False)
    is_final: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    language: Mapped[str] = mapped_column(Text, nullable=False)
    source_code: Mapped[str] = mapped_column(Text, nullable=False)
    execution_status: Mapped[CodeExecutionStatus] = mapped_column(
        pg_enum(CodeExecutionStatus, name="code_submissions_execution_status_enum"),
        nullable=False,
        default=CodeExecutionStatus.QUEUED,
    )
    executor: Mapped[str | None] = mapped_column(Text, nullable=True)
    passed_test_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_test_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_runtime_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    peak_memory_kb: Mapped[int | None] = mapped_column(Integer, nullable=True)
    graded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    answer: Mapped["Answer"] = relationship(back_populates="code_submissions")
    test_results: Mapped[list["CodeSubmissionTestResult"]] = relationship(
        back_populates="code_submission", cascade="all, delete-orphan"
    )


class CodeSubmissionTestResult(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "code_submission_test_results"
    __table_args__ = (UniqueConstraint("code_submission_id", "test_case_id"),)

    code_submission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("code_submissions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    test_case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("question_test_cases.id", ondelete="RESTRICT"),
        nullable=False,
    )
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    actual_output: Mapped[str | None] = mapped_column(Text, nullable=True)
    runtime_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    memory_kb: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stderr: Mapped[str | None] = mapped_column(Text, nullable=True)

    code_submission: Mapped["CodeSubmission"] = relationship(back_populates="test_results")
