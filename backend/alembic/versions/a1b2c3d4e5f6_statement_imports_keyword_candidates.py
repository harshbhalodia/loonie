"""statement imports, keyword candidates, reminders, jobs, budget history

Revision ID: a1b2c3d4e5f6
Revises: f6c8d3b5a2e7
Create Date: 2026-09-18 00:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'a1b2c3d4e5f6'
down_revision: str | None = 'f6c8d3b5a2e7'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'wealth_statement_imports',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('account_id', sa.String(), nullable=False),
        sa.Column('file_name', sa.String(), nullable=False),
        sa.Column('stored_path', sa.String(), nullable=True),
        sa.Column('source_type', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('transactions_json', sa.Text(), nullable=True),
        sa.Column('statement_period', sa.String(), nullable=True),
        sa.Column('transaction_count', sa.Integer(), nullable=False),
        sa.Column('inserted_count', sa.Integer(), nullable=False),
        sa.Column('updated_count', sa.Integer(), nullable=False),
        sa.Column('statement_balance', sa.Float(), nullable=True),
        sa.Column('minimum_due', sa.Float(), nullable=True),
        sa.Column('due_date', sa.Date(), nullable=True),
        sa.Column('paid', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('applied_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['account_id'], ['wealth_accounts.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('wealth_statement_imports', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_wealth_statement_imports_user_id'), ['user_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_wealth_statement_imports_account_id'), ['account_id'], unique=False)

    op.create_table(
        'wealth_keyword_candidates',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('keyword', sa.String(), nullable=False),
        sa.Column('sample_payee', sa.String(), nullable=True),
        sa.Column('occurrence_count', sa.Integer(), nullable=False),
        sa.Column('suggested_category_id', sa.String(), nullable=True),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['suggested_category_id'], ['wealth_categories.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('wealth_keyword_candidates', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_wealth_keyword_candidates_user_id'), ['user_id'], unique=False)

    op.create_table(
        'wealth_reminders',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('account_id', sa.String(), nullable=False),
        sa.Column('frequency', sa.String(), nullable=False),
        sa.Column('next_due_date', sa.Date(), nullable=False),
        sa.Column('last_completed_at', sa.Date(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['account_id'], ['wealth_accounts.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('wealth_reminders', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_wealth_reminders_user_id'), ['user_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_wealth_reminders_account_id'), ['account_id'], unique=False)

    op.create_table(
        'wealth_jobs',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('job_type', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('payload_json', sa.Text(), nullable=False),
        sa.Column('result_json', sa.Text(), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('finished_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('wealth_jobs', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_wealth_jobs_user_id'), ['user_id'], unique=False)

    op.create_table(
        'wealth_budget_history',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('budget_id', sa.String(), nullable=False),
        sa.Column('category_id', sa.String(), nullable=False),
        sa.Column('period', sa.String(), nullable=False),
        sa.Column('amount', sa.Float(), nullable=False),
        sa.Column('warning_threshold', sa.Float(), nullable=False),
        sa.Column('critical_threshold', sa.Float(), nullable=False),
        sa.Column('effective_from', sa.Date(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['budget_id'], ['wealth_budgets.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['category_id'], ['wealth_categories.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('wealth_budget_history', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_wealth_budget_history_user_id'), ['user_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_wealth_budget_history_budget_id'), ['budget_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('wealth_budget_history', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_wealth_budget_history_budget_id'))
        batch_op.drop_index(batch_op.f('ix_wealth_budget_history_user_id'))
    op.drop_table('wealth_budget_history')

    with op.batch_alter_table('wealth_jobs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_wealth_jobs_user_id'))
    op.drop_table('wealth_jobs')

    with op.batch_alter_table('wealth_reminders', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_wealth_reminders_account_id'))
        batch_op.drop_index(batch_op.f('ix_wealth_reminders_user_id'))
    op.drop_table('wealth_reminders')

    with op.batch_alter_table('wealth_keyword_candidates', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_wealth_keyword_candidates_user_id'))
    op.drop_table('wealth_keyword_candidates')

    with op.batch_alter_table('wealth_statement_imports', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_wealth_statement_imports_account_id'))
        batch_op.drop_index(batch_op.f('ix_wealth_statement_imports_user_id'))
    op.drop_table('wealth_statement_imports')
