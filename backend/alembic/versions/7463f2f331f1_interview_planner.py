"""interview planner

Revision ID: 7463f2f331f1
Revises: cadc0c718f96
Create Date: 2026-08-07 10:36:28.423118

Module 4 (Interview Planner & Session Setup) — purely additive on top of
the Module 1 baseline, which already created companies/roles/
interview_templates/template_rounds/interview_sessions/interview_rounds
empty and unused. Nothing existing is dropped, renamed, or narrowed.

Hand-adjusted from the autogenerate output, following the same pattern
Module 3's migration (cadc0c718f96) established:
  - server_default on every new NOT NULL column (so this applies cleanly
    even if rows already existed — they don't yet for these tables, but
    the pattern is kept consistent regardless).
  - add_column does not implicitly CREATE TYPE for a new native Postgres
    enum the way create_table does, so each new enum type is created
    explicitly before use and dropped explicitly in downgrade().
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '7463f2f331f1'
down_revision: Union[str, None] = 'cadc0c718f96'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


interview_sessions_mode_enum = postgresql.ENUM(
    'full_mock', 'technical_only', 'coding_only', 'behavioral_only', 'resume_deep_dive',
    name='interview_sessions_mode_enum',
)
interview_templates_mode_enum = postgresql.ENUM(
    'full_mock', 'technical_only', 'coding_only', 'behavioral_only', 'resume_deep_dive',
    name='interview_templates_mode_enum',
)
requested_difficulty_enum = postgresql.ENUM(
    'easy', 'medium', 'hard', 'auto', name='interview_sessions_requested_difficulty_enum',
)
starting_difficulty_enum = postgresql.ENUM(
    'easy', 'medium', 'hard', name='interview_sessions_starting_difficulty_enum',
)


def upgrade() -> None:
    bind = op.get_bind()
    interview_sessions_mode_enum.create(bind, checkfirst=True)
    interview_templates_mode_enum.create(bind, checkfirst=True)
    requested_difficulty_enum.create(bind, checkfirst=True)
    starting_difficulty_enum.create(bind, checkfirst=True)

    # --- companies ---------------------------------------------------
    op.add_column(
        'companies',
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
    )

    # --- roles ---------------------------------------------------------
    op.add_column('roles', sa.Column('role_key', sa.Text(), nullable=True))
    op.add_column(
        'roles',
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
    )
    op.create_index(op.f('ix_roles_role_key'), 'roles', ['role_key'], unique=False)

    # --- interview_templates -------------------------------------------
    op.add_column(
        'interview_templates',
        sa.Column(
            'mode',
            interview_templates_mode_enum,
            nullable=False,
            server_default='full_mock',
        ),
    )

    # --- interview_sessions ----------------------------------------------
    op.add_column(
        'interview_sessions',
        sa.Column(
            'requested_difficulty',
            requested_difficulty_enum,
            nullable=False,
            server_default='auto',
        ),
    )
    op.add_column(
        'interview_sessions',
        sa.Column(
            'starting_difficulty',
            starting_difficulty_enum,
            nullable=False,
            server_default='medium',
        ),
    )
    op.add_column(
        'interview_sessions',
        sa.Column(
            'mode', interview_sessions_mode_enum, nullable=False, server_default='full_mock'
        ),
    )
    op.add_column(
        'interview_sessions',
        sa.Column(
            'plan_snapshot',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    # Module 4 §8 — resume-optional interview modes. Relaxed here rather
    # than at table creation since Module 1's baseline required a resume
    # for every session unconditionally.
    op.alter_column('interview_sessions', 'resume_id', existing_type=sa.UUID(), nullable=True)


def downgrade() -> None:
    op.alter_column('interview_sessions', 'resume_id', existing_type=sa.UUID(), nullable=False)
    op.drop_column('interview_sessions', 'plan_snapshot')
    op.drop_column('interview_sessions', 'mode')
    op.drop_column('interview_sessions', 'starting_difficulty')
    op.drop_column('interview_sessions', 'requested_difficulty')

    op.drop_column('interview_templates', 'mode')

    op.drop_index(op.f('ix_roles_role_key'), table_name='roles')
    op.drop_column('roles', 'is_active')
    op.drop_column('roles', 'role_key')

    op.drop_column('companies', 'is_active')

    bind = op.get_bind()
    starting_difficulty_enum.drop(bind, checkfirst=True)
    requested_difficulty_enum.drop(bind, checkfirst=True)
    interview_templates_mode_enum.drop(bind, checkfirst=True)
    interview_sessions_mode_enum.drop(bind, checkfirst=True)
