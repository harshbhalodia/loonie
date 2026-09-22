from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import User, WealthBudget, WealthBudgetHistory, WealthCategory, WealthEntry
from app.schemas import BudgetHistorySummary, BudgetIn, BudgetOut
from app.services.analytics import compute_budget_history

router = APIRouter(prefix="/wealth/budgets", tags=["wealth:budgets"])

BUDGET_FIELDS = ("category_id", "period", "amount", "warning_threshold", "critical_threshold")


@router.get("", response_model=list[BudgetOut])
def list_budgets(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(WealthBudget).filter(WealthBudget.user_id == user.id).order_by(WealthBudget.created_at).all()


@router.get("/history", response_model=BudgetHistorySummary)
def budget_history(
    granularity: str = Query("month", pattern="^(month|quarter|year)$"),
    periods: int = Query(12, ge=1, le=60),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    budgets = db.query(WealthBudget).filter(WealthBudget.user_id == user.id).all()
    histories = db.query(WealthBudgetHistory).filter(WealthBudgetHistory.user_id == user.id).all()
    entries = db.query(WealthEntry).filter(WealthEntry.user_id == user.id).all()
    categories = db.query(WealthCategory).filter(WealthCategory.user_id == user.id).all()

    periods_result = compute_budget_history(
        budgets, histories, entries, categories, granularity=granularity, periods_back=periods
    )
    return {"granularity": granularity, "periods": periods_result}


@router.put("", response_model=BudgetOut)
def upsert_budget(payload: BudgetIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    budget = db.get(WealthBudget, payload.id) if payload.id else None
    if budget and budget.user_id != user.id:
        raise HTTPException(status_code=404, detail="Budget not found")

    if not budget:
        budget = WealthBudget(user_id=user.id)
        db.add(budget)
    else:
        changed = any(getattr(budget, field) != getattr(payload, field) for field in BUDGET_FIELDS)
        if changed:
            db.add(
                WealthBudgetHistory(
                    user_id=user.id,
                    budget_id=budget.id,
                    category_id=budget.category_id,
                    period=budget.period,
                    amount=budget.amount,
                    warning_threshold=budget.warning_threshold,
                    critical_threshold=budget.critical_threshold,
                    effective_from=date.today(),
                )
            )

    for field in BUDGET_FIELDS:
        setattr(budget, field, getattr(payload, field))

    db.commit()
    db.refresh(budget)
    return budget


@router.delete("/{budget_id}", status_code=204)
def delete_budget(budget_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    budget = db.get(WealthBudget, budget_id)
    if not budget or budget.user_id != user.id:
        raise HTTPException(status_code=404, detail="Budget not found")
    db.delete(budget)
    db.commit()
