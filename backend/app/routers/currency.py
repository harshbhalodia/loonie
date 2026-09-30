from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import User, WealthAccount, WealthAsset
from app.schemas import (
    BaseCurrencyIn,
    CurrencyOption,
    CurrencyOverview,
    ManualRateIn,
    SyncResultOut,
)
from app.services import fx
from app.services.analytics import compute_net_worth
from app.services.currencies import CURRENCIES, normalize_code

router = APIRouter(prefix="/wealth/currency", tags=["wealth:currency"])


def _overview(db: Session, user: User) -> CurrencyOverview:
    accounts = db.query(WealthAccount).filter(WealthAccount.user_id == user.id).all()
    assets = db.query(WealthAsset).filter(WealthAsset.user_id == user.id).all()
    used = fx.used_currencies(db, user.id)
    converted_accounts, converted_assets, _ = fx.to_base(db, user.id, accounts, assets)

    return CurrencyOverview(
        status=fx.status(db, user.id),
        rates=[
            {
                "currency": r.currency,
                "name": CURRENCIES.get(r.currency, r.currency),
                "rate_to_base": r.rate_to_base,
                "source": r.source,
                "as_of": r.as_of,
                "updated_at": r.updated_at,
                "in_use": r.currency in used,
            }
            for r in fx.list_rate_rows(db, user.id)
        ],
        breakdown=fx.net_worth_by_currency(db, user.id, accounts, assets),
        net_worth_base=compute_net_worth(converted_accounts, converted_assets)["total"],
    )


def _code(raw: str, user_base: str) -> str:
    code = normalize_code(raw, "")
    if not code:
        raise HTTPException(status_code=422, detail="Currency must be a 3-letter code such as EUR")
    if code == user_base:
        raise HTTPException(status_code=422, detail=f"{code} is your base currency and always equals 1")
    return code


@router.get("/catalog", response_model=list[CurrencyOption])
def catalog():
    return [{"code": code, "name": name} for code, name in CURRENCIES.items()]


@router.get("", response_model=CurrencyOverview)
def overview(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    fx.ensure_rates(db, user.id)
    return _overview(db, user)


@router.put("/base", response_model=CurrencyOverview)
def change_base(payload: BaseCurrencyIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    fx.set_base_currency(db, user.id, payload.base_currency, payload.relabel_existing)
    try:
        fx.sync_rates(db, user.id)
    except fx.FxError:
        pass  # keeps the rebased rates; the overview shows any that are missing
    return _overview(db, user)


@router.post("/sync", response_model=SyncResultOut)
def sync(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        result = fx.sync_rates(db, user.id)
    except fx.FxError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return SyncResultOut(
        updated=result.updated,
        skipped_manual=result.skipped_manual,
        unavailable=result.unavailable,
        provider=result.provider,
        overview=_overview(db, user),
    )


@router.post("/rates/{code}/live", response_model=CurrencyOverview)
def use_live_rate(code: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Adds a currency to track, or reverts a hand-typed rate back to the live one."""
    clean = _code(code, fx.get_base_currency(db, user.id))
    try:
        fx.track_or_revert_live(db, user.id, clean)
    except fx.FxError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return _overview(db, user)


@router.put("/rates/{code}", response_model=CurrencyOverview)
def set_manual_rate(
    code: str, payload: ManualRateIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    clean = _code(code, fx.get_base_currency(db, user.id))
    fx.set_manual_rate(db, user.id, clean, payload.rate_to_base)
    return _overview(db, user)


@router.delete("/rates/{code}", response_model=CurrencyOverview)
def remove_rate(code: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Stops tracking a currency. One still used by an account/asset is fetched again on the next sync."""
    clean = _code(code, fx.get_base_currency(db, user.id))
    fx.remove_rate(db, user.id, clean)
    return _overview(db, user)
