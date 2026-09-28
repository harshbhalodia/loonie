"""marketplace_installed_blueprints table

Revision ID: e2a9c4f7b1d3
Revises: c9e1a4d7f3b2
Create Date: 2026-09-27 00:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'e2a9c4f7b1d3'
down_revision: str | None = 'c9e1a4d7f3b2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'marketplace_installed_blueprints',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('blueprint_id', sa.String(), nullable=False),
        sa.Column('version', sa.String(), nullable=False),
        sa.Column('tier', sa.String(), nullable=False),
        sa.Column('license_token', sa.String(), nullable=True),
        sa.Column('installed_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'blueprint_id', name='uq_marketplace_install_user_blueprint'),
    )
    op.create_index(
        op.f('ix_marketplace_installed_blueprints_user_id'), 'marketplace_installed_blueprints', ['user_id']
    )
    op.create_index(
        op.f('ix_marketplace_installed_blueprints_blueprint_id'), 'marketplace_installed_blueprints', ['blueprint_id']
    )


def downgrade() -> None:
    op.drop_index(
        op.f('ix_marketplace_installed_blueprints_blueprint_id'), table_name='marketplace_installed_blueprints'
    )
    op.drop_index(op.f('ix_marketplace_installed_blueprints_user_id'), table_name='marketplace_installed_blueprints')
    op.drop_table('marketplace_installed_blueprints')
