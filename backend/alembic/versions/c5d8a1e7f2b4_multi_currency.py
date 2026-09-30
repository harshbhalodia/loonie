"""multi-currency: asset currency, base-currency settings, FX rates

Revision ID: c5d8a1e7f2b4
Revises: a7c3e9f1b4d2
Create Date: 2026-09-29 00:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'c5d8a1e7f2b4'
down_revision: str | None = 'a7c3e9f1b4d2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('wealth_assets') as batch_op:
        batch_op.add_column(sa.Column('currency', sa.String(), nullable=False, server_default='USD'))

    op.create_table(
        'wealth_currency_settings',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('base_currency', sa.String(), nullable=False, server_default='USD'),
        sa.Column('last_synced_at', sa.DateTime(), nullable=True),
        sa.Column('last_attempt_at', sa.DateTime(), nullable=True),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id'),
    )
    op.create_index(op.f('ix_wealth_currency_settings_user_id'), 'wealth_currency_settings', ['user_id'])

    op.create_table(
        'wealth_fx_rates',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('currency', sa.String(), nullable=False),
        sa.Column('rate_to_base', sa.Float(), nullable=False),
        sa.Column('source', sa.String(), nullable=False, server_default='live'),
        sa.Column('as_of', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'currency', name='uq_fx_rate_user_currency'),
    )
    op.create_index(op.f('ix_wealth_fx_rates_user_id'), 'wealth_fx_rates', ['user_id'])


def downgrade() -> None:
    op.drop_index(op.f('ix_wealth_fx_rates_user_id'), table_name='wealth_fx_rates')
    op.drop_table('wealth_fx_rates')
    op.drop_index(op.f('ix_wealth_currency_settings_user_id'), table_name='wealth_currency_settings')
    op.drop_table('wealth_currency_settings')
    with op.batch_alter_table('wealth_assets') as batch_op:
        batch_op.drop_column('currency')
