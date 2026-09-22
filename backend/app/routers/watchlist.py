from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import User, WealthWatchlistItem
from app.schemas import WatchlistItemIn, WatchlistItemOut

router = APIRouter(prefix="/wealth/watchlist", tags=["wealth:watchlist"])

WATCHLIST_FIELDS = (
    "name",
    "item_type",
    "symbol",
    "status",
    "target_price",
    "current_price",
    "currency",
    "thesis",
    "url",
    "priority",
)


@router.get("", response_model=list[WatchlistItemOut])
def list_watchlist(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return (
        db.query(WealthWatchlistItem)
        .filter(WealthWatchlistItem.user_id == user.id)
        .order_by(WealthWatchlistItem.priority.desc(), WealthWatchlistItem.created_at.desc())
        .all()
    )


@router.put("", response_model=WatchlistItemOut)
def upsert_watchlist_item(payload: WatchlistItemIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    item = db.get(WealthWatchlistItem, payload.id) if payload.id else None
    if item and item.user_id != user.id:
        raise HTTPException(status_code=404, detail="Watchlist item not found")

    if not item:
        item = WealthWatchlistItem(user_id=user.id)
        db.add(item)

    for field in WATCHLIST_FIELDS:
        setattr(item, field, getattr(payload, field))

    db.commit()
    db.refresh(item)
    return item


@router.delete("/{item_id}", status_code=204)
def delete_watchlist_item(item_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    item = db.get(WealthWatchlistItem, item_id)
    if not item or item.user_id != user.id:
        raise HTTPException(status_code=404, detail="Watchlist item not found")
    db.delete(item)
    db.commit()
