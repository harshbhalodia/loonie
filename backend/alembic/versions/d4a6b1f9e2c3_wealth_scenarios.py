"""wealth scenarios (sandbox what-if drafts, never touch real accounts/assets/entries)

Revision ID: d4a6b1f9e2c3
Revises: c3f5a9d2e8b1
Create Date: 2026-09-16 00:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'd4a6b1f9e2c3'
down_revision: str | None = 'c3f5a9d2e8b1'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'wealth_scenarios',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('scenario_type', sa.String(), nullable=False),
        sa.Column('years_horizon', sa.Integer(), nullable=False),
        sa.Column('investment_return_rate', sa.Float(), nullable=False),
        sa.Column('personal_asset_growth_rate', sa.Float(), nullable=False),
        sa.Column('monthly_contribution_override', sa.Float(), nullable=True),
        sa.Column('income_growth_rate', sa.Float(), nullable=False),
        sa.Column('is_adopted', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('wealth_scenarios', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_wealth_scenarios_user_id'), ['user_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('wealth_scenarios', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_wealth_scenarios_user_id'))
    op.drop_table('wealth_scenarios')
