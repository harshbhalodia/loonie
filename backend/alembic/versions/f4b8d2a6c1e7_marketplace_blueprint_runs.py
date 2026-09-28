"""marketplace_blueprint_runs table (run history + local feedback)

Revision ID: f4b8d2a6c1e7
Revises: e2a9c4f7b1d3
Create Date: 2026-09-27 00:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'f4b8d2a6c1e7'
down_revision: str | None = 'e2a9c4f7b1d3'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'marketplace_blueprint_runs',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('blueprint_id', sa.String(), nullable=False),
        sa.Column('blueprint_version', sa.String(), nullable=False),
        sa.Column('tier', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('facts_json', sa.Text(), nullable=False),
        sa.Column('result', sa.Text(), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('user_rating', sa.String(), nullable=True),
        sa.Column('user_note', sa.Text(), nullable=True),
        sa.Column('shared_with_publisher_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_marketplace_blueprint_runs_user_id'), 'marketplace_blueprint_runs', ['user_id'])
    op.create_index(
        op.f('ix_marketplace_blueprint_runs_blueprint_id'), 'marketplace_blueprint_runs', ['blueprint_id']
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_marketplace_blueprint_runs_blueprint_id'), table_name='marketplace_blueprint_runs')
    op.drop_index(op.f('ix_marketplace_blueprint_runs_user_id'), table_name='marketplace_blueprint_runs')
    op.drop_table('marketplace_blueprint_runs')
