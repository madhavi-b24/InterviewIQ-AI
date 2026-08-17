"""interview execution

Revision ID: 4df563d9a10b
Revises: 7463f2f331f1
Create Date: 2026-08-17 14:53:20.797747

Module 5 (LangGraph Adaptive Interview Engine) — purely additive: two
nullable FK columns, nothing else. Every other column Module 5 needs
(interview_sessions.status/current_round_sequence/current_difficulty,
interview_rounds.status, questions.*, answers.*, answer_evaluations.*)
already exists from the Module 1 baseline. Round-length policy and
follow-up caps are Module-5-owned constants (app/agents/policy.py), not
schema — no column needed for those.

Hand-adjusted from the autogenerate output: the raw output passed `None`
as the constraint name to both `create_foreign_key` calls, which would
have let Postgres auto-assign a name at create time but then failed at
`downgrade()` (`drop_constraint(None, ...)` requires an actual name, this
project's Base metadata has no naming-convention that could resolve
`None`). Named explicitly here instead, following Postgres's own default
`<table>_<column>_fkey` convention so the names are exactly what an
unnamed constraint would have received anyway — just made deterministic
and drop-able.

Both new columns create a genuine circular FK reference across
interview_sessions -> questions -> interview_rounds -> interview_sessions
(alembic's autogenerate comparison warns about this, "SAWarning: cannot
correctly sort tables"). This is intentional and safe: both new columns
are nullable with `ON DELETE SET NULL`, so there's no insert-order/
delete-order problem in practice — a session's current_question_id and a
question's parent_question_id are always set only after the referenced
row already exists.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4df563d9a10b'
down_revision: Union[str, None] = '7463f2f331f1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('interview_sessions', sa.Column('current_question_id', sa.UUID(), nullable=True))
    op.create_foreign_key(
        'interview_sessions_current_question_id_fkey',
        'interview_sessions',
        'questions',
        ['current_question_id'],
        ['id'],
        ondelete='SET NULL',
    )
    op.add_column('questions', sa.Column('parent_question_id', sa.UUID(), nullable=True))
    op.create_foreign_key(
        'questions_parent_question_id_fkey',
        'questions',
        'questions',
        ['parent_question_id'],
        ['id'],
        ondelete='SET NULL',
    )


def downgrade() -> None:
    op.drop_constraint('questions_parent_question_id_fkey', 'questions', type_='foreignkey')
    op.drop_column('questions', 'parent_question_id')
    op.drop_constraint(
        'interview_sessions_current_question_id_fkey', 'interview_sessions', type_='foreignkey'
    )
    op.drop_column('interview_sessions', 'current_question_id')
