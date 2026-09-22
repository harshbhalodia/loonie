from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import (
    User,
    WealthAccount,
    WealthAsset,
    WealthEntry,
    WealthScenario,
    WealthScenarioAccountConfig,
    WealthScenarioAssetConfig,
    WealthScenarioIncomeSource,
)
from app.schemas import ScenarioIn, ScenarioOut, ScenarioProjectionPoint
from app.services.analytics import compute_cashflow_series, project_scenario

router = APIRouter(prefix="/wealth/scenarios", tags=["wealth:scenarios"])

SCENARIO_FIELDS = (
    "name",
    "description",
    "scenario_type",
    "years_horizon",
    "investment_return_rate",
    "personal_asset_growth_rate",
    "monthly_contribution_override",
    "income_growth_rate",
    "is_adopted",
)


@router.get("", response_model=list[ScenarioOut])
def list_scenarios(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return (
        db.query(WealthScenario)
        .filter(WealthScenario.user_id == user.id)
        .order_by(WealthScenario.created_at.desc())
        .all()
    )


@router.put("", response_model=ScenarioOut)
def upsert_scenario(payload: ScenarioIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    scenario = db.get(WealthScenario, payload.id) if payload.id else None
    if scenario and scenario.user_id != user.id:
        raise HTTPException(status_code=404, detail="Scenario not found")

    if not scenario:
        scenario = WealthScenario(user_id=user.id)
        db.add(scenario)

    if payload.is_adopted:
        # Only one scenario can be "the plan" at a time — this is a label only, never touches real data.
        db.query(WealthScenario).filter(WealthScenario.user_id == user.id).update({"is_adopted": False})

    for field in SCENARIO_FIELDS:
        setattr(scenario, field, getattr(payload, field))

    # Overrides are always fully replaced on save (this is a draft, not an append-only ledger) —
    # silently drop any account/asset id that isn't the user's own.
    owned_account_ids = {a.id for a in db.query(WealthAccount.id).filter(WealthAccount.user_id == user.id)}
    owned_asset_ids = {a.id for a in db.query(WealthAsset.id).filter(WealthAsset.user_id == user.id)}

    scenario.account_configs = [
        WealthScenarioAccountConfig(
            account_id=c.account_id, growth_rate=c.growth_rate, include_in_growth=c.include_in_growth
        )
        for c in payload.account_configs
        if c.account_id in owned_account_ids
    ]
    scenario.asset_configs = [
        WealthScenarioAssetConfig(asset_id=c.asset_id, growth_rate=c.growth_rate, include_in_growth=c.include_in_growth)
        for c in payload.asset_configs
        if c.asset_id in owned_asset_ids
    ]
    scenario.income_sources = [
        WealthScenarioIncomeSource(name=s.name, monthly_amount=s.monthly_amount, growth_rate=s.growth_rate)
        for s in payload.income_sources
    ]

    db.commit()
    db.refresh(scenario)
    return scenario


@router.delete("/{scenario_id}", status_code=204)
def delete_scenario(scenario_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    scenario = db.get(WealthScenario, scenario_id)
    if not scenario or scenario.user_id != user.id:
        raise HTTPException(status_code=404, detail="Scenario not found")
    db.delete(scenario)
    db.commit()


@router.get("/{scenario_id}/projection", response_model=list[ScenarioProjectionPoint])
def scenario_projection(scenario_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    scenario = db.get(WealthScenario, scenario_id)
    if not scenario or scenario.user_id != user.id:
        raise HTTPException(status_code=404, detail="Scenario not found")

    accounts = db.query(WealthAccount).filter(WealthAccount.user_id == user.id).all()
    assets = db.query(WealthAsset).filter(WealthAsset.user_id == user.id).all()
    entries = db.query(WealthEntry).filter(WealthEntry.user_id == user.id).all()

    cashflow = compute_cashflow_series(entries, months_back=3)
    avg_monthly_net = sum(c["net"] for c in cashflow) / len(cashflow) if cashflow else 0.0

    return project_scenario(accounts, assets, scenario, avg_monthly_net)
