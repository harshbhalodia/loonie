from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import User, WealthAsset
from app.schemas import AssetIn, AssetOut, AssetSellIn

router = APIRouter(prefix="/wealth/assets", tags=["wealth:assets"])


@router.get("", response_model=list[AssetOut])
def list_assets(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(WealthAsset).filter(WealthAsset.user_id == user.id).order_by(WealthAsset.created_at).all()


@router.put("", response_model=AssetOut)
def upsert_asset(payload: AssetIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    asset = db.get(WealthAsset, payload.id) if payload.id else None
    if asset and asset.user_id != user.id:
        raise HTTPException(status_code=404, detail="Asset not found")

    if not asset:
        asset = WealthAsset(user_id=user.id)
        db.add(asset)

    for field in (
        "name",
        "asset_type",
        "purchase_value",
        "purchase_date",
        "current_value",
        "current_value_updated_at",
        "notes",
    ):
        setattr(asset, field, getattr(payload, field))

    db.commit()
    db.refresh(asset)
    return asset


@router.post("/{asset_id}/sell", response_model=AssetOut)
def sell_asset(asset_id: str, payload: AssetSellIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    asset = db.get(WealthAsset, asset_id)
    if not asset or asset.user_id != user.id:
        raise HTTPException(status_code=404, detail="Asset not found")
    asset.status = "sold"
    asset.sold_value = payload.sold_value
    asset.sold_date = payload.sold_date or date.today()
    db.commit()
    db.refresh(asset)
    return asset


@router.post("/{asset_id}/reopen", response_model=AssetOut)
def reopen_asset(asset_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    asset = db.get(WealthAsset, asset_id)
    if not asset or asset.user_id != user.id:
        raise HTTPException(status_code=404, detail="Asset not found")
    asset.status = "holding"
    asset.sold_value = None
    asset.sold_date = None
    db.commit()
    db.refresh(asset)
    return asset


@router.delete("/{asset_id}", status_code=204)
def delete_asset(asset_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    asset = db.get(WealthAsset, asset_id)
    if not asset or asset.user_id != user.id:
        raise HTTPException(status_code=404, detail="Asset not found")
    db.delete(asset)
    db.commit()
