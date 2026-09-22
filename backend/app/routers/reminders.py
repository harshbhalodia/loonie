"""Recurring reminders to upload/reconcile an account's statement, so records stay current."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import User, WealthReminder
from app.schemas import ReminderIn, ReminderOut
from app.services.reminders import advance_due_date

router = APIRouter(prefix="/wealth/reminders", tags=["wealth:reminders"])


def _with_is_due(reminder: WealthReminder) -> dict:
    return {**reminder.__dict__, "is_due": reminder.is_active and reminder.next_due_date <= date.today()}


@router.get("", response_model=list[ReminderOut])
def list_reminders(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    reminders = db.query(WealthReminder).filter(WealthReminder.user_id == user.id).order_by(WealthReminder.next_due_date).all()
    return [_with_is_due(r) for r in reminders]


@router.put("", response_model=ReminderOut)
def upsert_reminder(payload: ReminderIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    reminder = db.get(WealthReminder, payload.id) if payload.id else None
    if reminder and reminder.user_id != user.id:
        raise HTTPException(status_code=404, detail="Reminder not found")

    if not reminder:
        reminder = WealthReminder(user_id=user.id)
        db.add(reminder)

    reminder.account_id = payload.account_id
    reminder.frequency = payload.frequency
    reminder.next_due_date = payload.next_due_date or advance_due_date(date.today(), payload.frequency)
    reminder.is_active = payload.is_active

    db.commit()
    db.refresh(reminder)
    return _with_is_due(reminder)


@router.delete("/{reminder_id}", status_code=204)
def delete_reminder(reminder_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    reminder = db.get(WealthReminder, reminder_id)
    if not reminder or reminder.user_id != user.id:
        raise HTTPException(status_code=404, detail="Reminder not found")
    db.delete(reminder)
    db.commit()
