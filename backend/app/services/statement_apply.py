"""Applies reviewed statement transactions to wealth_entries as an upsert (not a blind insert),
so re-uploading/re-applying the same statement updates existing rows and only adds what's
missing instead of creating duplicates every time.
"""
from __future__ import annotations

from app.models import WealthEntry
from app.schemas import StatementApplyTransaction
from app.services import keyword_learning
from app.services.ledger import sync_account_balance, sync_goal_progress

ENTRY_FIELDS = ("type", "amount", "entry_date", "payee", "category_id", "goal_id")


def _dedupe_key(entry_date, amount: float, payee: str | None) -> tuple:
    return (entry_date, round(amount, 2), (payee or "").strip().lower())


def apply_statement_transactions(
    db,
    user_id: str,
    account_id: str,
    import_batch_id: str,
    transactions: list[StatementApplyTransaction],
) -> tuple[int, int, int]:
    """Returns (inserted_count, updated_count, uncategorized_candidate_count)."""
    existing = db.query(WealthEntry).filter(WealthEntry.account_id == account_id).all()
    existing_by_key = {_dedupe_key(e.entry_date, e.amount, e.payee): e for e in existing}

    inserted_count = 0
    updated_count = 0
    candidate_count = 0
    touched_goal_ids: set[str] = set()

    for tx in transactions:
        key = _dedupe_key(tx.entry_date, tx.amount, tx.payee)
        entry = existing_by_key.get(key)

        if entry:
            for field in ENTRY_FIELDS:
                setattr(entry, field, getattr(tx, field))
            entry.import_batch_id = import_batch_id
            db.add(entry)
            updated_count += 1
        else:
            entry = WealthEntry(user_id=user_id, account_id=account_id, import_batch_id=import_batch_id)
            for field in ENTRY_FIELDS:
                setattr(entry, field, getattr(tx, field))
            db.add(entry)
            existing_by_key[key] = entry
            inserted_count += 1

        if tx.goal_id:
            touched_goal_ids.add(tx.goal_id)
        if not tx.category_id:
            keyword_learning.record_uncategorized_candidate(db, user_id, tx.payee)
            candidate_count += 1

    db.commit()

    for goal_id in touched_goal_ids:
        sync_goal_progress(db, goal_id)
    sync_account_balance(db, account_id)

    return inserted_count, updated_count, candidate_count
