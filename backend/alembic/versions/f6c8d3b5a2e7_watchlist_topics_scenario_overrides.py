"""watchlist items, research topics, scenario account/asset overrides + extra income sources

Revision ID: f6c8d3b5a2e7
Revises: e5b7c2a4f1d9
Create Date: 2026-09-16 00:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'f6c8d3b5a2e7'
down_revision: str | None = 'e5b7c2a4f1d9'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'wealth_watchlist_items',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('item_type', sa.String(), nullable=False),
        sa.Column('symbol', sa.String(), nullable=True),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('target_price', sa.Float(), nullable=True),
        sa.Column('current_price', sa.Float(), nullable=True),
        sa.Column('currency', sa.String(), nullable=False),
        sa.Column('thesis', sa.Text(), nullable=True),
        sa.Column('url', sa.String(), nullable=True),
        sa.Column('priority', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('wealth_watchlist_items', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_wealth_watchlist_items_user_id'), ['user_id'], unique=False)

    op.create_table(
        'wealth_topics',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('category', sa.String(), nullable=True),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('related_goal_id', sa.String(), nullable=True),
        sa.Column('priority', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['related_goal_id'], ['wealth_goals.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('wealth_topics', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_wealth_topics_user_id'), ['user_id'], unique=False)

    op.create_table(
        'wealth_scenario_account_configs',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('scenario_id', sa.String(), nullable=False),
        sa.Column('account_id', sa.String(), nullable=False),
        sa.Column('growth_rate', sa.Float(), nullable=True),
        sa.Column('include_in_growth', sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(['scenario_id'], ['wealth_scenarios.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['account_id'], ['wealth_accounts.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('wealth_scenario_account_configs', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_wealth_scenario_account_configs_scenario_id'), ['scenario_id'], unique=False)

    op.create_table(
        'wealth_scenario_asset_configs',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('scenario_id', sa.String(), nullable=False),
        sa.Column('asset_id', sa.String(), nullable=False),
        sa.Column('growth_rate', sa.Float(), nullable=True),
        sa.Column('include_in_growth', sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(['scenario_id'], ['wealth_scenarios.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['asset_id'], ['wealth_assets.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('wealth_scenario_asset_configs', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_wealth_scenario_asset_configs_scenario_id'), ['scenario_id'], unique=False)

    op.create_table(
        'wealth_scenario_income_sources',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('scenario_id', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('monthly_amount', sa.Float(), nullable=False),
        sa.Column('growth_rate', sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(['scenario_id'], ['wealth_scenarios.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('wealth_scenario_income_sources', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_wealth_scenario_income_sources_scenario_id'), ['scenario_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('wealth_scenario_income_sources', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_wealth_scenario_income_sources_scenario_id'))
    op.drop_table('wealth_scenario_income_sources')

    with op.batch_alter_table('wealth_scenario_asset_configs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_wealth_scenario_asset_configs_scenario_id'))
    op.drop_table('wealth_scenario_asset_configs')

    with op.batch_alter_table('wealth_scenario_account_configs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_wealth_scenario_account_configs_scenario_id'))
    op.drop_table('wealth_scenario_account_configs')

    with op.batch_alter_table('wealth_topics', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_wealth_topics_user_id'))
    op.drop_table('wealth_topics')

    with op.batch_alter_table('wealth_watchlist_items', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_wealth_watchlist_items_user_id'))
    op.drop_table('wealth_watchlist_items')
