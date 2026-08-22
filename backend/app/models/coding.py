"""Coding-problem catalog (Module 6) — mirrors app/models/planning.py's
shape exactly: a small set of maintainable, seed-driven catalog entities
(module §8: "do not hardcode coding problems directly inside service
methods"). A round never points a live Question at a mutable catalog row
directly — selecting a problem SNAPSHOTS it into a Question (question_type
=coding) + QuestionTestCase rows at selection time, the same "catalog is
mutable, live instances are immutable copies" pattern Module 4 already
established for interview_templates/template_rounds ->
interview_sessions.plan_snapshot/interview_rounds.
"""

import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, Numeric, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin
from app.models.enums import DifficultyLevel, pg_enum


class CodingProblem(Base, UUIDPrimaryKeyMixin, CreatedAtMixin):
    __tablename__ = "coding_problems"

    # Natural key for idempotent seeding (mirrors companies.slug) — never
    # exposed as "the" id to clients, who only ever see the uuid pk.
    slug: Mapped[str] = mapped_column(Text, unique=True, nullable=False, index=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    difficulty: Mapped[DifficultyLevel] = mapped_column(
        pg_enum(DifficultyLevel, name="coding_problems_difficulty_enum"), nullable=False
    )
    # Free-form topic tags (module §8: arrays/strings/hash maps/binary
    # search/stacks-queues/trees/graphs/dynamic programming, ...) — a fixed
    # enum would need a migration every time a new topic tag is wanted;
    # these are catalog labels, not values anything branches on in code.
    topics: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    constraints: Mapped[str | None] = mapped_column(Text, nullable=True)
    expected_time_complexity: Mapped[str | None] = mapped_column(Text, nullable=True)
    expected_space_complexity: Mapped[str | None] = mapped_column(Text, nullable=True)
    # e.g. ["python", "java", "cpp"] — must be a subset of
    # app/execution/docker_sandbox.py's LANGUAGE_CONFIGS keys; not FK'd to
    # anything since the language set is server-controlled config, not
    # another catalog table (module §6).
    supported_languages: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    # {"python": "def solve(nums):\n    ...", "java": "..."} — optional
    # per-language scaffold shown to the candidate; never required.
    starter_code: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # Optional metadata for future filtering (module §8: "company/role
    # metadata where useful") — role_key values, matching
    # app/services/resume/role_profiles.json's taxonomy (Module 3/4's
    # "one taxonomy, not two" rule applies here too. Empty = generic,
    # matches every role.
    role_keys: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    test_cases: Mapped[list["CodingProblemTestCase"]] = relationship(
        back_populates="problem",
        cascade="all, delete-orphan",
        order_by="CodingProblemTestCase.sequence_no",
    )


class CodingProblemTestCase(Base, UUIDPrimaryKeyMixin):
    """Catalog-side test cases — copied into `question_test_cases` rows
    when a problem is selected for a live round (never referenced live by
    `Question`/`QuestionTestCase`, same snapshot rationale as the module
    docstring above).
    """

    __tablename__ = "coding_problem_test_cases"
    __table_args__ = (UniqueConstraint("problem_id", "sequence_no"),)

    problem_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("coding_problems.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    input: Mapped[str] = mapped_column(Text, nullable=False)
    expected_output: Mapped[str] = mapped_column(Text, nullable=False)
    is_sample: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    weight: Mapped[float] = mapped_column(Numeric(4, 2), nullable=False, default=1.00)
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False)

    problem: Mapped["CodingProblem"] = relationship(back_populates="test_cases")
