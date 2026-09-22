"""wealth category rules (keyword -> category mapping for statement auto-categorization)

Revision ID: c3f5a9d2e8b1
Revises: b2e4f8a1c6d7
Create Date: 2026-09-16 00:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'c3f5a9d2e8b1'
down_revision: str | None = 'b2e4f8a1c6d7'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'wealth_category_rules',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('keyword', sa.String(), nullable=False),
        sa.Column('category_id', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['category_id'], ['wealth_categories.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('wealth_category_rules', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_wealth_category_rules_user_id'), ['user_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('wealth_category_rules', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_wealth_category_rules_user_id'))
    op.drop_table('wealth_category_rules')
