from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import User, WealthEntry
from app.schemas import EntryIn, EntryOut
from app.services.ledger import sync_account_balance, sync_goal_progress

router = APIRouter(prefix="/wealth/entries", tags=["wealth:entries"])

ENTRY_FIELDS = (
    "type",
    "amount",
    "entry_date",
    "payee",
    "category_id",
    "account_id",
    "goal_id",
    "is_recurring",
    "recurrence_interval",
    "notes",
    "import_batch_id",
)


@router.get("", response_model=list[EntryOut])
def list_entries(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return (
        db.query(WealthEntry)
        .filter(WealthEntry.user_id == user.id)
        .order_by(WealthEntry.entry_date.desc())
        .all()
    )


@router.put("", response_model=EntryOut)
def upsert_entry(payload: EntryIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    entry = db.get(WealthEntry, payload.id) if payload.id else None
    if entry and entry.user_id != user.id:
        raise HTTPException(status_code=404, detail="Entry not found")

    previous_goal_id = entry.goal_id if entry else None
    previous_account_id = entry.account_id if entry else None

    if not entry:
        entry = WealthEntry(user_id=user.id)
        db.add(entry)

    for field in ENTRY_FIELDS:
        setattr(entry, field, getattr(payload, field))

    db.commit()
    db.refresh(entry)

    if previous_goal_id and previous_goal_id != entry.goal_id:
        sync_goal_progress(db, previous_goal_id)
    if entry.goal_id:
        sync_goal_progress(db, entry.goal_id)

    if previous_account_id and previous_account_id != entry.account_id:
        sync_account_balance(db, previous_account_id)
    sync_account_balance(db, entry.account_id)

    return entry


@router.post("/bulk", response_model=list[EntryOut])
def bulk_insert_entries(payload: list[EntryIn], user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    created: list[WealthEntry] = []
    for item in payload:
        entry = WealthEntry(user_id=user.id)
        for field in ENTRY_FIELDS:
            setattr(entry, field, getattr(item, field))
        db.add(entry)
        created.append(entry)

    db.commit()
    for entry in created:
        db.refresh(entry)

    for goal_id in {e.goal_id for e in created if e.goal_id}:
        sync_goal_progress(db, goal_id)

    for account_id in {e.account_id for e in created if e.account_id}:
        sync_account_balance(db, account_id)

    return created


@router.delete("/{entry_id}", status_code=204)
def delete_entry(entry_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    entry = db.get(WealthEntry, entry_id)
    if not entry or entry.user_id != user.id:
        raise HTTPException(status_code=404, detail="Entry not found")
    goal_id = entry.goal_id
    account_id = entry.account_id
    db.delete(entry)
    db.commit()
    if goal_id:
        sync_goal_progress(db, goal_id)
    if account_id:
        sync_account_balance(db, account_id)
