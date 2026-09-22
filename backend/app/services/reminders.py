"""Recurring reminders to keep an account's statement uploads/reconciliation up to date."""
from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.models import WealthReminder


def _add_months(d: date, months: int) -> date:
    month_index = d.month - 1 + months
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    day = min(d.day, monthrange(year, month)[1])
    return date(year, month, day)


def advance_due_date(base: date, frequency: str) -> date:
    if frequency == "weekly":
        return base + timedelta(weeks=1)
    if frequency == "biweekly":
        return base + timedelta(weeks=2)
    if frequency == "semi_monthly":
        return base + timedelta(days=15)
    if frequency == "monthly":
        return _add_months(base, 1)
    if frequency == "quarterly":
        return _add_months(base, 3)
    if frequency == "yearly":
        return _add_months(base, 12)
    raise ValueError(f"Unknown reminder frequency: {frequency}")


def mark_account_statement_uploaded(db: Session, account_id: str, today: date | None = None) -> None:
    """Called after a statement is successfully applied for an account — pushes every active
    reminder tied to that account forward to its next occurrence."""
    today = today or date.today()
    reminders = (
        db.query(WealthReminder)
        .filter(WealthReminder.account_id == account_id, WealthReminder.is_active.is_(True))
        .all()
    )
    for reminder in reminders:
        reminder.last_completed_at = today
        reminder.next_due_date = advance_due_date(today, reminder.frequency)
        db.add(reminder)
    if reminders:
        db.commit()
