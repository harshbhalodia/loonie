from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import User, WealthAccount
from app.schemas import AccountIn, AccountOut
from app.services.ledger import sync_account_balance

router = APIRouter(prefix="/wealth/accounts", tags=["wealth:accounts"])


@router.get("", response_model=list[AccountOut])
def list_accounts(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(WealthAccount).filter(WealthAccount.user_id == user.id).order_by(WealthAccount.created_at).all()


@router.put("", response_model=AccountOut)
def upsert_account(payload: AccountIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    account = db.get(WealthAccount, payload.id) if payload.id else None
    if account and account.user_id != user.id:
        raise HTTPException(status_code=404, detail="Account not found")

    if not account:
        account = WealthAccount(user_id=user.id)
        db.add(account)

    for field in (
        "name",
        "type",
        "institution",
        "currency",
        "opening_balance",
        "current_balance",
        "is_liquid",
        "balance_source",
    ):
        setattr(account, field, getattr(payload, field))

    db.commit()
    db.refresh(account)

    # Only accounts opted into balance_source="computed" get their balance overwritten here.
    sync_account_balance(db, account.id)
    db.refresh(account)
    return account


@router.delete("/{account_id}", status_code=204)
def delete_account(account_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    account = db.get(WealthAccount, account_id)
    if not account or account.user_id != user.id:
        raise HTTPException(status_code=404, detail="Account not found")
    db.delete(account)
    db.commit()
