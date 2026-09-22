"""Keeps WealthAccount.current_balance in sync with its linked entries — opt-in only.

An account's balance is only derived from entries when `balance_source == "computed"`, which
the user must explicitly turn on (default is "manual"). This matters because entries linked to
an account rarely capture 100% of its real cash movements (e.g. transfers, interest, cash
withdrawals) — deriving a balance purely from `opening_balance + income - expense` for an
account that wasn't backfilled with a matching opening_balance and every transaction will
produce a wildly wrong number. Accounts default to "manual" so linking entries to an account
never silently overwrites a balance the user maintains by hand.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import WealthAccount, WealthEntry, WealthGoal


def sync_goal_progress(db: Session, goal_id: str | None) -> None:
    """Recomputes a goal's current_amount from its linked entries and auto-marks it achieved
    the first time it reaches its target. Manual current_amount edits are only used for goals
    with no linked entries at all."""
    if not goal_id:
        return
    goal = db.get(WealthGoal, goal_id)
    if not goal:
        return
    linked_total = db.query(func.sum(WealthEntry.amount)).filter(WealthEntry.goal_id == goal_id).scalar()
    if linked_total is not None:
        goal.current_amount = round(linked_total, 2)
    if goal.achieved_at is None and goal.target_amount > 0 and goal.current_amount >= goal.target_amount:
        goal.achieved_at = date.today()
    db.add(goal)
    db.commit()


def sync_account_balance(db: Session, account_id: str | None) -> None:
    if not account_id:
        return
    account = db.get(WealthAccount, account_id)
    if not account or account.balance_source != "computed":
        return

    totals = (
        db.query(WealthEntry.type, func.sum(WealthEntry.amount))
        .filter(WealthEntry.account_id == account_id)
        .group_by(WealthEntry.type)
        .all()
    )
    total_by_type = dict(totals)
    income = total_by_type.get("income") or 0.0
    expense = total_by_type.get("expense") or 0.0
    account.current_balance = round(account.opening_balance + income - expense, 2)
    db.add(account)
    db.commit()
