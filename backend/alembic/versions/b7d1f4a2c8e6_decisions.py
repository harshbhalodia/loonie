"""decisions table (Jev-powered decision agent)

Revision ID: b7d1f4a2c8e6
Revises: a1b2c3d4e5f6
Create Date: 2026-09-19 00:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'b7d1f4a2c8e6'
down_revision: str | None = 'a1b2c3d4e5f6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'decisions',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('question', sa.Text(), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('options_json', sa.Text(), nullable=False),
        sa.Column('chosen_option', sa.String(), nullable=True),
        sa.Column('confidence', sa.Float(), nullable=True),
        sa.Column('probabilities_json', sa.Text(), nullable=True),
        sa.Column('profile_snapshot_json', sa.Text(), nullable=True),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_decisions_user_id'), 'decisions', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_decisions_user_id'), table_name='decisions')
    op.drop_table('decisions')
