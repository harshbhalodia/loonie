from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import User, WealthForecastAssumption
from app.schemas import AssumptionIn, AssumptionOut

router = APIRouter(prefix="/wealth/assumptions", tags=["wealth:assumptions"])


@router.get("", response_model=list[AssumptionOut])
def list_assumptions(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return (
        db.query(WealthForecastAssumption)
        .filter(WealthForecastAssumption.user_id == user.id)
        .order_by(WealthForecastAssumption.created_at)
        .all()
    )


@router.put("", response_model=AssumptionOut)
def upsert_assumption(payload: AssumptionIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    assumption = db.get(WealthForecastAssumption, payload.id) if payload.id else None
    if assumption and assumption.user_id != user.id:
        raise HTTPException(status_code=404, detail="Assumption not found")

    if not assumption:
        assumption = WealthForecastAssumption(user_id=user.id)
        db.add(assumption)

    if payload.is_active:
        db.query(WealthForecastAssumption).filter(WealthForecastAssumption.user_id == user.id).update(
            {"is_active": False}
        )

    for field in ("name", "annual_return_rate", "inflation_rate", "years_horizon", "is_active"):
        setattr(assumption, field, getattr(payload, field))

    db.commit()
    db.refresh(assumption)
    return assumption
