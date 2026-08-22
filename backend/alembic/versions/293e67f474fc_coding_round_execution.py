"""coding round execution

Revision ID: 293e67f474fc
Revises: 4df563d9a10b
Create Date: 2026-08-22 12:10:28.307087

Module 6 (Real Coding Round & Code Evaluation Engine) — purely additive,
following the same hand-adjustment pattern every prior migration in this
chain established (server_default on every new NOT NULL column, explicit
enum handling where autogenerate doesn't cover it).

Four independent pieces:
  1. `coding_problems` / `coding_problem_test_cases` — brand new catalog
     tables (mirrors `interview_templates`/`template_rounds`). Their enum
     column's Postgres type (`coding_problems_difficulty_enum`) is
     auto-created by `create_table` (unlike `add_column`, which needs an
     explicit CREATE TYPE — see `7463f2f331f1`'s docstring) but is NOT
     auto-dropped by `drop_table`, so `downgrade()` drops it explicitly.
  2. `coding_evaluations` gets 6 additive nullable-turned-NOT-NULL columns
     (all with server_default so this applies cleanly even though the
     table currently has zero rows — nothing has ever written to it).
  3. `code_submissions.execution_status`'s existing Postgres enum type
     (`code_submissions_execution_status_enum`) gains 4 new values
     (`compile_error`, `runtime_error`, `memory_limit`, `output_limit` —
     module §7's granular status list; `TIME_LIMIT`/`EXECUTION_ERROR`
     reuse the already-existing `timeout`/`error` values instead of
     adding near-duplicates — see app/models/enums.py's
     CodeExecutionStatus docstring for the full mapping). Postgres has no
     `ALTER TYPE ... DROP VALUE` — removing an enum value cleanly requires
     rebuilding the whole type (create new, migrate column, drop old,
     rename), which is real but disproportionate ceremony for a downgrade
     path on values nothing has been written with yet. `downgrade()`
     documents this as a known one-way step rather than silently
     pretending it's reversible.
  4. `questions` gains two nullable columns, `coding_problem_id` (FK,
     RESTRICT) and `coding_snapshot` (jsonb) — populated only when
     question_type=coding, NULL for every other question (see
     app/models/interview.py's Question docstring). Nullable, no
     server_default needed: existing rows are all non-coding.
  5. `code_submissions` gains one nullable column, `error_message` (text)
     — the compiler's own message or a genuine infra-failure message; NULL
     for every other outcome. Nullable, no server_default needed.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '293e67f474fc'
down_revision: Union[str, None] = '4df563d9a10b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- coding_problems / coding_problem_test_cases (new catalog) -------
    op.create_table(
        'coding_problems',
        sa.Column('slug', sa.Text(), nullable=False),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column(
            'difficulty',
            sa.Enum('easy', 'medium', 'hard', name='coding_problems_difficulty_enum'),
            nullable=False,
        ),
        sa.Column(
            'topics',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column('constraints', sa.Text(), nullable=True),
        sa.Column('expected_time_complexity', sa.Text(), nullable=True),
        sa.Column('expected_space_complexity', sa.Text(), nullable=True),
        sa.Column(
            'supported_languages',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            'starter_code',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            'role_keys',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column(
            'created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_coding_problems_slug'), 'coding_problems', ['slug'], unique=True)

    op.create_table(
        'coding_problem_test_cases',
        sa.Column('problem_id', sa.UUID(), nullable=False),
        sa.Column('input', sa.Text(), nullable=False),
        sa.Column('expected_output', sa.Text(), nullable=False),
        sa.Column('is_sample', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column(
            'weight',
            sa.Numeric(precision=4, scale=2),
            nullable=False,
            server_default=sa.text('1.00'),
        ),
        sa.Column('sequence_no', sa.Integer(), nullable=False),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(['problem_id'], ['coding_problems.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('problem_id', 'sequence_no'),
    )
    op.create_index(
        op.f('ix_coding_problem_test_cases_problem_id'),
        'coding_problem_test_cases',
        ['problem_id'],
        unique=False,
    )

    # --- questions: additive coding-round columns (nullable, no
    # server_default needed — every existing row is non-coding) ------------
    op.add_column('questions', sa.Column('coding_problem_id', sa.UUID(), nullable=True))
    op.add_column(
        'questions',
        sa.Column('coding_snapshot', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.create_index(
        op.f('ix_questions_coding_problem_id'), 'questions', ['coding_problem_id'], unique=False
    )
    op.create_foreign_key(
        'fk_questions_coding_problem_id_coding_problems',
        'questions',
        'coding_problems',
        ['coding_problem_id'],
        ['id'],
        ondelete='RESTRICT',
    )

    # --- code_submissions: additive error_message column (nullable) -------
    op.add_column('code_submissions', sa.Column('error_message', sa.Text(), nullable=True))

    # --- coding_evaluations additive columns ------------------------------
    op.add_column(
        'coding_evaluations',
        sa.Column(
            'edge_case_score',
            sa.Numeric(precision=5, scale=2),
            nullable=False,
            server_default=sa.text('0'),
        ),
    )
    op.add_column(
        'coding_evaluations',
        sa.Column('edge_case_explanation', sa.Text(), nullable=False, server_default=sa.text("''")),
    )
    op.add_column(
        'coding_evaluations',
        sa.Column(
            'overall_code_score',
            sa.Numeric(precision=5, scale=2),
            nullable=False,
            server_default=sa.text('0'),
        ),
    )
    op.add_column(
        'coding_evaluations',
        sa.Column(
            'strengths',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        'coding_evaluations',
        sa.Column(
            'weaknesses',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        'coding_evaluations',
        sa.Column(
            'recommendations',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )

    # --- code_submissions.execution_status: additive enum values ----------
    for value in ('compile_error', 'runtime_error', 'memory_limit', 'output_limit'):
        op.execute(
            f"ALTER TYPE code_submissions_execution_status_enum ADD VALUE IF NOT EXISTS '{value}'"
        )


def downgrade() -> None:
    # Postgres cannot drop individual enum values — see module docstring.
    # The 4 values added above are left in place; nothing that downgrade
    # removes below ever references them, so this is safe, just one-way.

    op.drop_column('coding_evaluations', 'recommendations')
    op.drop_column('coding_evaluations', 'weaknesses')
    op.drop_column('coding_evaluations', 'strengths')
    op.drop_column('coding_evaluations', 'overall_code_score')
    op.drop_column('coding_evaluations', 'edge_case_explanation')
    op.drop_column('coding_evaluations', 'edge_case_score')

    op.drop_column('code_submissions', 'error_message')

    op.drop_constraint(
        'fk_questions_coding_problem_id_coding_problems', 'questions', type_='foreignkey'
    )
    op.drop_index(op.f('ix_questions_coding_problem_id'), table_name='questions')
    op.drop_column('questions', 'coding_snapshot')
    op.drop_column('questions', 'coding_problem_id')

    op.drop_index(
        op.f('ix_coding_problem_test_cases_problem_id'), table_name='coding_problem_test_cases'
    )
    op.drop_table('coding_problem_test_cases')
    op.drop_index(op.f('ix_coding_problems_slug'), table_name='coding_problems')
    op.drop_table('coding_problems')

    bind = op.get_bind()
    sa.Enum(name='coding_problems_difficulty_enum').drop(bind, checkfirst=True)
