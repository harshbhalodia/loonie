"""configurable category groups, yearly budgets, fiscal year, goal-entry linking

Revision ID: 9f1c2b7a5e3d
Revises: 82a8e2647cb8
Create Date: 2026-09-15 00:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '9f1c2b7a5e3d'
down_revision: str | None = '82a8e2647cb8'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Seed groups created for every existing user, in display order. Mirrors the previous
# hardcoded CategoryGroup enum so existing categories map over losslessly.
_DEFAULT_GROUPS = [
    ("fixed", "Fixed", "#2f6d4f", True),
    ("variable", "Variable", "#a15c07", True),
    ("adhoc", "Adhoc", "#b3261e", False),
    ("investments", "Investments", "#275475", False),
    ("new_investments", "New Investments", "#6d4fa1", False),
    ("income", "Income", "#1f4d38", False),
]


def upgrade() -> None:
    import uuid
    from datetime import datetime

    bind = op.get_bind()

    op.add_column('users', sa.Column('fiscal_year_start_month', sa.Integer(), nullable=False, server_default='1'))

    op.create_table(
        'wealth_category_groups',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('color', sa.String(), nullable=True),
        sa.Column('sort_order', sa.Integer(), nullable=False),
        sa.Column('is_essential', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('wealth_category_groups', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_wealth_category_groups_user_id'), ['user_id'], unique=False)

    op.add_column('wealth_categories', sa.Column('group_id', sa.String(), nullable=True))

    # --- data backfill: one set of default groups per user, then remap categories.group -> group_id ---
    users = bind.execute(sa.text('SELECT id FROM users')).fetchall()
    now = datetime.utcnow()
    group_table = sa.table(
        'wealth_category_groups',
        sa.column('id', sa.String()),
        sa.column('user_id', sa.String()),
        sa.column('name', sa.String()),
        sa.column('color', sa.String()),
        sa.column('sort_order', sa.Integer()),
        sa.column('is_essential', sa.Boolean()),
        sa.column('created_at', sa.DateTime()),
    )
    categories_table = sa.table(
        'wealth_categories',
        sa.column('id', sa.String()),
        sa.column('user_id', sa.String()),
        sa.column('group_id', sa.String()),
    )

    for (user_id,) in users:
        slug_to_id: dict[str, str] = {}
        for order, (slug, label, color, is_essential) in enumerate(_DEFAULT_GROUPS):
            group_id = str(uuid.uuid4())
            slug_to_id[slug] = group_id
            bind.execute(
                group_table.insert().values(
                    id=group_id,
                    user_id=user_id,
                    name=label,
                    color=color,
                    sort_order=order,
                    is_essential=is_essential,
                    created_at=now,
                )
            )

        for slug, group_id in slug_to_id.items():
            bind.execute(
                categories_table.update()
                .where(categories_table.c.user_id == user_id)
                .where(sa.text("`group` = :slug"))
                .values(group_id=group_id),
                {"slug": slug},
            )

    with op.batch_alter_table('wealth_categories', schema=None) as batch_op:
        batch_op.drop_column('group')

    op.add_column('wealth_budgets', sa.Column('period', sa.String(), nullable=False, server_default='monthly'))
    with op.batch_alter_table('wealth_budgets', schema=None) as batch_op:
        batch_op.alter_column('monthly_amount', new_column_name='amount')

    op.add_column('wealth_goals', sa.Column('achieved_at', sa.Date(), nullable=True))

    op.add_column('wealth_entries', sa.Column('goal_id', sa.String(), nullable=True))
    with op.batch_alter_table('wealth_entries', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_wealth_entries_goal_id'), ['goal_id'], unique=False)
        batch_op.create_foreign_key(
            'fk_wealth_entries_goal_id', 'wealth_goals', ['goal_id'], ['id'], ondelete='SET NULL'
        )


def downgrade() -> None:
    with op.batch_alter_table('wealth_entries', schema=None) as batch_op:
        batch_op.drop_constraint('fk_wealth_entries_goal_id', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_wealth_entries_goal_id'))
        batch_op.drop_column('goal_id')

    op.drop_column('wealth_goals', 'achieved_at')

    with op.batch_alter_table('wealth_budgets', schema=None) as batch_op:
        batch_op.alter_column('amount', new_column_name='monthly_amount')
    op.drop_column('wealth_budgets', 'period')

    op.add_column('wealth_categories', sa.Column('group', sa.String(), nullable=False, server_default='variable'))
    with op.batch_alter_table('wealth_categories', schema=None) as batch_op:
        batch_op.drop_column('group_id')

    op.drop_table('wealth_category_groups')
    op.drop_column('users', 'fiscal_year_start_month')
