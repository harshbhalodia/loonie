from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import User, WealthAccount, WealthAsset, WealthBudget, WealthCategory, WealthCategoryGroup, WealthEntry, WealthForecastAssumption, WealthGoal
from app.schemas import AnalyticsSummary, NetWorthProjectionPoint
from app.services.analytics import (
    compute_asset_performance,
    compute_budget_statuses,
    compute_cashflow_series,
    compute_category_group_breakdown,
    compute_diversification,
    compute_goal_feasibility,
    compute_income_forecast,
    compute_liquidity,
    compute_net_worth,
    project_net_worth,
)

router = APIRouter(prefix="/wealth/analytics", tags=["wealth:analytics"])


def _load(db: Session, user_id: str):
    accounts = db.query(WealthAccount).filter(WealthAccount.user_id == user_id).all()
    categories = db.query(WealthCategory).filter(WealthCategory.user_id == user_id).all()
    groups = db.query(WealthCategoryGroup).filter(WealthCategoryGroup.user_id == user_id).all()
    entries = db.query(WealthEntry).filter(WealthEntry.user_id == user_id).all()
    budgets = db.query(WealthBudget).filter(WealthBudget.user_id == user_id).all()
    assets = db.query(WealthAsset).filter(WealthAsset.user_id == user_id).all()
    goals = db.query(WealthGoal).filter(WealthGoal.user_id == user_id).all()
    return accounts, categories, groups, entries, budgets, assets, goals


@router.get("/summary", response_model=AnalyticsSummary)
def analytics_summary(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    accounts, categories, groups, entries, budgets, assets, goals = _load(db, user.id)

    recent_cashflow = compute_cashflow_series(entries, months_back=3)
    avg_monthly_net = sum(c["net"] for c in recent_cashflow) / len(recent_cashflow) if recent_cashflow else 0.0

    return AnalyticsSummary(
        net_worth=compute_net_worth(accounts, assets),
        liquidity=compute_liquidity(accounts, entries, categories, groups),
        cashflow=compute_cashflow_series(entries, months_back=12),
        category_breakdown=compute_category_group_breakdown(entries, categories, groups),
        budget_statuses=compute_budget_statuses(budgets, entries, categories, user.fiscal_year_start_month),
        asset_performance=compute_asset_performance(assets),
        income_forecast=compute_income_forecast(entries),
        diversification=compute_diversification(accounts, assets),
        goal_feasibility=compute_goal_feasibility(goals, avg_monthly_net),
    )


@router.get("/projection", response_model=list[NetWorthProjectionPoint])
def analytics_projection(
    assumption_id: str | None = Query(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    accounts = db.query(WealthAccount).filter(WealthAccount.user_id == user.id).all()
    entries = db.query(WealthEntry).filter(WealthEntry.user_id == user.id).all()
    assets = db.query(WealthAsset).filter(WealthAsset.user_id == user.id).all()

    if assumption_id:
        assumption = db.get(WealthForecastAssumption, assumption_id)
    else:
        assumption = (
            db.query(WealthForecastAssumption)
            .filter(WealthForecastAssumption.user_id == user.id, WealthForecastAssumption.is_active.is_(True))
            .first()
        )

    if not assumption or assumption.user_id != user.id:
        raise HTTPException(status_code=404, detail="No forecast assumption configured")

    cashflow = compute_cashflow_series(entries, months_back=3)
    avg_monthly_net = sum(c["net"] for c in cashflow) / len(cashflow) if cashflow else 0.0

    return project_net_worth(accounts, assumption, avg_monthly_net, assets)
