"""Runs a marketplace blueprint's scenario-by-scenario stress test against a user's own
already-computed wealth analytics — same never-invent-numbers grounding as services/agents.py,
just driven by a declarative BlueprintDefinition (YAML scenario list) instead of Python code.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models import User, WealthAccount, WealthAsset, WealthCategory, WealthCategoryGroup, WealthEntry, WealthGoal
from app.services import ai_provider, wealth_scopes
from app.services.analytics import (
    compute_cashflow_series,
    compute_diversification,
    compute_goal_feasibility,
    compute_income_forecast,
    compute_liquidity,
    compute_net_worth,
)
from app.services.marketplace_catalog import BlueprintDefinition


class ConsentRequiredError(RuntimeError):
    """Raised when a blueprint's declared inputs are not fully covered by the user's granted
    data scopes. Never silently narrowed/ignored — the run is refused outright so a partial,
    unreviewed grant can never be mistaken for a full one."""

    def __init__(self, missing_scopes: list[str]) -> None:
        self.missing_scopes = missing_scopes
        super().__init__(f"Missing data-sharing consent for: {', '.join(missing_scopes)}")


@dataclass
class BlueprintRunOutcome:
    result: str
    facts: dict
    shared_scopes: list[str]


def _gather_snapshot(db: Session, user: User) -> dict:
    accounts = db.query(WealthAccount).filter(WealthAccount.user_id == user.id).all()
    assets = db.query(WealthAsset).filter(WealthAsset.user_id == user.id).all()
    entries = db.query(WealthEntry).filter(WealthEntry.user_id == user.id).all()
    categories = db.query(WealthCategory).filter(WealthCategory.user_id == user.id).all()
    groups = db.query(WealthCategoryGroup).filter(WealthCategoryGroup.user_id == user.id).all()
    goals = db.query(WealthGoal).filter(WealthGoal.user_id == user.id).all()

    cashflow = compute_cashflow_series(entries, months_back=6)
    avg_monthly_net = sum(c["net"] for c in cashflow) / len(cashflow) if cashflow else 0.0

    return {
        "net_worth": compute_net_worth(accounts, assets),
        "liquidity": compute_liquidity(accounts, entries, categories, groups),
        "cashflow": cashflow,
        "diversification": compute_diversification(accounts, assets),
        "income_forecast": compute_income_forecast(entries),
        "goal_feasibility": compute_goal_feasibility(goals, avg_monthly_net),
    }


def run_blueprint(
    db: Session, user: User, definition: BlueprintDefinition, granted_scopes: list[str]
) -> BlueprintRunOutcome:
    """Runs every scenario in `definition` as a narrow specialist call, then a lead-synthesis
    call. Returns the final narrative plus the exact facts/scopes it was grounded in, so callers
    can persist a full, honest run record.

    `granted_scopes` is the user's EXPLICIT, previously-recorded consent (see
    services/wealth_scopes.py) — this function never trusts `definition.inputs` alone. Any
    requested scope not present in `granted_scopes` blocks the run entirely with
    `ConsentRequiredError` before any data is gathered or any AI call is made (fail closed, no
    partial/best-effort run). A blueprint that declares no inputs is sent no data at all —
    empty inputs is never treated as "send everything".
    Raises `ai_provider.AIProviderError` if the local AI is disabled/unreachable — callers must
    handle this and degrade gracefully."""
    requested = [f for f in definition.inputs if f in wealth_scopes.known_scope_ids()]
    granted = set(granted_scopes)
    missing = [f for f in requested if f not in granted]
    if missing:
        raise ConsentRequiredError(missing)

    # Local reasoning models (e.g. qwen3.6) can take well over the default 60s per call even for
    # a short answer (chain-of-thought overhead) — a multi-scenario blueprint issues several
    # sequential calls, so use the same generous timeout as statements.py/decision_agent.py.
    timeout = 300

    snapshot = _gather_snapshot(db, user)
    facts_dict = {key: snapshot.get(key) for key in requested}
    facts = json.dumps(facts_dict, indent=2, default=str)

    notes = []
    for scenario in definition.scenarios:
        note = ai_provider.generate(
            definition.specialist_system_prompt,
            f"Scenario: {scenario.description}\n\nClient's verified data:\n{facts}",
            timeout=timeout,
        )
        notes.append(f"[{scenario.id}] {scenario.description}\n{note}")

    lead_prompt = definition.lead_system_prompt.format(disclaimer=definition.disclaimer)
    lead_input = f"Headline figures:\n{facts}\n\n" + "\n\n".join(notes)
    result = ai_provider.generate(lead_prompt, lead_input, timeout=timeout)
    return BlueprintRunOutcome(result=result, facts=facts_dict, shared_scopes=requested)
