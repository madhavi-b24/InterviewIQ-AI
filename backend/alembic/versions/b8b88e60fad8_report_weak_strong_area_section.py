"""report weak strong area section

Revision ID: b8b88e60fad8
Revises: 293e67f474fc
Create Date: 2026-08-23 11:09:25.686256

Module 8 (Progress Dashboard) — purely additive, one nullable column on
each of `report_weak_areas`/`report_strong_areas`. A genuine gap found
during Module 8 planning, not an invented feature: Module 7's
ReportService already knows which of the five report sections a weak/
strong-area topic belongs to (it's the same signal used to compute
`report_weak_areas.severity`) but never wrote it down. Module 8's
skill_progress needs that link to score a topic against the *correct*
`report_section_scores` row instead of guessing — see
app/services/progress/progress_service.py.

Nullable, no server_default needed: every row from a report generated
before this migration simply has section=NULL, and ProgressService skips
those rather than guessing (a self-resolving gap — every report generated
after this migration has it). Same "add_column needs an explicit CREATE
TYPE" pattern every prior migration in this chain establishes (see
7463f2f331f1's docstring) — two new Postgres enum types, one per column,
matching how `report_section_scores.section` already has its own
distinct type for the same ReportSection Python enum.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'b8b88e60fad8'
down_revision: Union[str, None] = '293e67f474fc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


report_weak_areas_section_enum = postgresql.ENUM(
    'technical', 'coding', 'communication', 'problem_solving', 'confidence',
    name='report_weak_areas_section_enum',
)
report_strong_areas_section_enum = postgresql.ENUM(
    'technical', 'coding', 'communication', 'problem_solving', 'confidence',
    name='report_strong_areas_section_enum',
)


def upgrade() -> None:
    bind = op.get_bind()
    report_weak_areas_section_enum.create(bind, checkfirst=True)
    report_strong_areas_section_enum.create(bind, checkfirst=True)

    op.add_column(
        'report_weak_areas',
        sa.Column('section', report_weak_areas_section_enum, nullable=True),
    )
    op.add_column(
        'report_strong_areas',
        sa.Column('section', report_strong_areas_section_enum, nullable=True),
    )


def downgrade() -> None:
    op.drop_column('report_strong_areas', 'section')
    op.drop_column('report_weak_areas', 'section')

    bind = op.get_bind()
    report_strong_areas_section_enum.drop(bind, checkfirst=True)
    report_weak_areas_section_enum.drop(bind, checkfirst=True)
