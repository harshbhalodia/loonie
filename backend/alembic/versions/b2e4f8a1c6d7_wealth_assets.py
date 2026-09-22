"""wealth assets (home, car, etc. held outside financial accounts)

Revision ID: b2e4f8a1c6d7
Revises: 9f1c2b7a5e3d
Create Date: 2026-09-15 00:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'b2e4f8a1c6d7'
down_revision: str | None = '9f1c2b7a5e3d'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'wealth_assets',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('asset_type', sa.String(), nullable=False),
        sa.Column('purchase_value', sa.Float(), nullable=False),
        sa.Column('purchase_date', sa.Date(), nullable=True),
        sa.Column('current_value', sa.Float(), nullable=False),
        sa.Column('current_value_updated_at', sa.Date(), nullable=True),
        sa.Column('status', sa.String(), nullable=False, server_default='holding'),
        sa.Column('sold_value', sa.Float(), nullable=True),
        sa.Column('sold_date', sa.Date(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('wealth_assets', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_wealth_assets_user_id'), ['user_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('wealth_assets', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_wealth_assets_user_id'))
    op.drop_table('wealth_assets')
