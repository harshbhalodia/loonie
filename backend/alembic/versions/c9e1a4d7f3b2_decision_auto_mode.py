"""decision context/plan files + auto-mode sessions

Revision ID: c9e1a4d7f3b2
Revises: b7d1f4a2c8e6
Create Date: 2026-09-19 00:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'c9e1a4d7f3b2'
down_revision: str | None = 'b7d1f4a2c8e6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'decision_context',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id'),
    )
    op.create_table(
        'decision_plan',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id'),
    )
    op.create_table(
        'decision_auto_sessions',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('plan_brief', sa.Text(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('rounds_completed', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_decision_auto_sessions_user_id'), 'decision_auto_sessions', ['user_id'], unique=False)

    with op.batch_alter_table('decisions') as batch_op:
        batch_op.add_column(sa.Column('session_id', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('round_number', sa.Integer(), nullable=True))
        batch_op.create_index(op.f('ix_decisions_session_id'), ['session_id'], unique=False)
        batch_op.create_foreign_key(
            'fk_decisions_session_id_decision_auto_sessions', 'decision_auto_sessions', ['session_id'], ['id'], ondelete='SET NULL'
        )


def downgrade() -> None:
    with op.batch_alter_table('decisions') as batch_op:
        batch_op.drop_constraint('fk_decisions_session_id_decision_auto_sessions', type_='foreignkey')
        batch_op.drop_index(op.f('ix_decisions_session_id'))
        batch_op.drop_column('round_number')
        batch_op.drop_column('session_id')

    op.drop_index(op.f('ix_decision_auto_sessions_user_id'), table_name='decision_auto_sessions')
    op.drop_table('decision_auto_sessions')
    op.drop_table('decision_plan')
    op.drop_table('decision_context')
