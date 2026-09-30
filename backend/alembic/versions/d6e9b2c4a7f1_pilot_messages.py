"""pilot_messages: the endless Pilot chat history

Revision ID: d6e9b2c4a7f1
Revises: c5d8a1e7f2b4
Create Date: 2026-09-29 12:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'd6e9b2c4a7f1'
down_revision: str | None = 'c5d8a1e7f2b4'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'pilot_messages',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('role', sa.String(), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('payload_json', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_pilot_messages_user_id'), 'pilot_messages', ['user_id'])
    op.create_index(op.f('ix_pilot_messages_created_at'), 'pilot_messages', ['created_at'])


def downgrade() -> None:
    op.drop_index(op.f('ix_pilot_messages_created_at'), table_name='pilot_messages')
    op.drop_index(op.f('ix_pilot_messages_user_id'), table_name='pilot_messages')
    op.drop_table('pilot_messages')
