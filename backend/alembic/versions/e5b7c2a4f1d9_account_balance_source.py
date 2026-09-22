"""account balance_source (manual vs computed) — opt-in entry-derived balance tracking

Revision ID: e5b7c2a4f1d9
Revises: d4a6b1f9e2c3
Create Date: 2026-09-16 00:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'e5b7c2a4f1d9'
down_revision: str | None = 'd4a6b1f9e2c3'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('wealth_accounts', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('balance_source', sa.String(), nullable=False, server_default='manual')
        )


def downgrade() -> None:
    with op.batch_alter_table('wealth_accounts', schema=None) as batch_op:
        batch_op.drop_column('balance_source')
