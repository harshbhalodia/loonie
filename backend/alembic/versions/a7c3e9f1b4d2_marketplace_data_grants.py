"""marketplace_data_grants table + shared_scopes_json on marketplace_blueprint_runs

Revision ID: a7c3e9f1b4d2
Revises: f4b8d2a6c1e7
Create Date: 2026-09-27 00:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'a7c3e9f1b4d2'
down_revision: str | None = 'f4b8d2a6c1e7'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'marketplace_data_grants',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('blueprint_id', sa.String(), nullable=False),
        sa.Column('blueprint_version', sa.String(), nullable=False),
        sa.Column('granted_scopes_json', sa.Text(), nullable=False),
        sa.Column('granted_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'blueprint_id', name='uq_marketplace_grant_user_blueprint'),
    )
    op.create_index(op.f('ix_marketplace_data_grants_user_id'), 'marketplace_data_grants', ['user_id'])
    op.create_index(op.f('ix_marketplace_data_grants_blueprint_id'), 'marketplace_data_grants', ['blueprint_id'])

    with op.batch_alter_table('marketplace_blueprint_runs') as batch_op:
        batch_op.add_column(sa.Column('shared_scopes_json', sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('marketplace_blueprint_runs') as batch_op:
        batch_op.drop_column('shared_scopes_json')

    op.drop_index(op.f('ix_marketplace_data_grants_blueprint_id'), table_name='marketplace_data_grants')
    op.drop_index(op.f('ix_marketplace_data_grants_user_id'), table_name='marketplace_data_grants')
    op.drop_table('marketplace_data_grants')
