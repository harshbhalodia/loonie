"""Wealth agents: read-only over computed facts, write only to wealth_insights.

Agents never receive raw database access or arbitrary SQL — they are handed a
JSON snapshot of numbers already computed by app.services.analytics and asked
only to explain/interpret them. This keeps every dollar amount deterministic;
the LLM's job is limited to language, not arithmetic.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from app.models import User, WealthAccount, WealthAsset, WealthBudget, WealthCategory, WealthCategoryGroup, WealthEntry, WealthForecastAssumption, WealthGoal, WealthScenario, WealthTopic, WealthWatchlistItem
from app.services import ai_provider
from app.services.analytics import (
    compute_asset_performance,
    compute_budget_statuses,
    compute_cashflow_series,
    compute_diversification,
    compute_goal_feasibility,
    compute_income_forecast,
    compute_liquidity,
    compute_net_worth,
    project_net_worth,
    project_scenario,
)


@dataclass
class AgentSpec:
    id: str
    name: str
    version: str
    description: str
    reads: list[str]
    writes: list[str]


AGENTS: dict[str, AgentSpec] = {
    "wealth.budget_analyzer": AgentSpec(
        id="wealth.budget_analyzer",
        name="Budget Analyzer",
        version="0.1.0",
        description="Flags categories that are over, or trending over, their monthly budget.",
        reads=["wealth_entries", "wealth_budgets", "wealth_categories"],
        writes=["wealth_insights"],
    ),
    "wealth.financial_insight_agent": AgentSpec(
        id="wealth.financial_insight_agent",
        name="Financial Insight Agent",
        version="0.1.0",
        description="Combines net worth, liquidity and cashflow into a plain-language summary.",
        reads=["wealth_accounts", "wealth_entries", "wealth_categories"],
        writes=["wealth_insights"],
    ),
    "wealth.asset_advisor": AgentSpec(
        id="wealth.asset_advisor",
        name="Asset Advisor",
        version="0.1.0",
        description="Reviews held assets' purchase vs current value and suggests whether to hold, sell, or buy more.",
        reads=["wealth_assets"],
        writes=["wealth_insights"],
    ),
    "wealth.risk_hedging_agent": AgentSpec(
        id="wealth.risk_hedging_agent",
        name="Risk Hedging Agent",
        version="0.1.0",
        description="Reviews liquidity buffers and asset concentration to flag hedging gaps — thin emergency funds or over-exposure to one asset class.",
        reads=["wealth_accounts", "wealth_assets", "wealth_entries", "wealth_categories"],
        writes=["wealth_insights"],
    ),
    "wealth.diversification_agent": AgentSpec(
        id="wealth.diversification_agent",
        name="Diversification Agent",
        version="0.1.0",
        description="Breaks down where net worth sits across account and asset types and flags concentration risk.",
        reads=["wealth_accounts", "wealth_assets"],
        writes=["wealth_insights"],
    ),
    "wealth.investment_planner": AgentSpec(
        id="wealth.investment_planner",
        name="Investment Planner",
        version="0.1.0",
        description="Combines net worth, cashflow, income forecast and the active projection assumption into investment planning suggestions.",
        reads=["wealth_accounts", "wealth_assets", "wealth_entries", "wealth_forecast_assumptions"],
        writes=["wealth_insights"],
    ),
    "wealth.goal_planner": AgentSpec(
        id="wealth.goal_planner",
        name="Goal Planner",
        version="0.1.0",
        description="Checks each goal's required monthly contribution against your savings rate and suggests realistic goals or timeline changes.",
        reads=["wealth_goals", "wealth_entries"],
        writes=["wealth_insights"],
    ),
    "wealth.scenario_strategist": AgentSpec(
        id="wealth.scenario_strategist",
        name="Scenario Strategist",
        version="0.1.0",
        description="Compares your saved sandbox what-if drafts' assumed contributions against your real savings rate and highlights which projected outcome is both realistic and best.",
        reads=["wealth_scenarios", "wealth_accounts", "wealth_assets", "wealth_entries"],
        writes=["wealth_insights"],
    ),
    "wealth.research_advisor": AgentSpec(
        id="wealth.research_advisor",
        name="Research Advisor",
        version="0.1.0",
        description="Reviews your watchlist and research topics against your goals and savings rate, and suggests which few deserve your attention first.",
        reads=["wealth_watchlist_items", "wealth_topics", "wealth_goals", "wealth_entries"],
        writes=["wealth_insights"],
    ),
}

SYSTEM_PROMPT = """You are a personal finance assistant inside LifeOS.
You are given ONLY pre-computed, trusted numeric facts as JSON — never invent, estimate, \
or recompute a number that is not present in the facts. Distinguish clearly between facts \
(given), and your interpretation/recommendation (your own words). Be concise: 3-5 sentences, \
plain language, no markdown headers. If nothing needs attention, say so briefly."""


def _gather_budget_facts(db: Session, user: User) -> dict:
    entries = db.query(WealthEntry).filter(WealthEntry.user_id == user.id).all()
    budgets = db.query(WealthBudget).filter(WealthBudget.user_id == user.id).all()
    categories = db.query(WealthCategory).filter(WealthCategory.user_id == user.id).all()
    statuses = compute_budget_statuses(budgets, entries, categories, user.fiscal_year_start_month)
    return {"month": date.today().isoformat()[:7], "budgets": statuses}


def _gather_financial_insight_facts(db: Session, user: User) -> dict:
    accounts = db.query(WealthAccount).filter(WealthAccount.user_id == user.id).all()
    entries = db.query(WealthEntry).filter(WealthEntry.user_id == user.id).all()
    categories = db.query(WealthCategory).filter(WealthCategory.user_id == user.id).all()
    groups = db.query(WealthCategoryGroup).filter(WealthCategoryGroup.user_id == user.id).all()

    return {
        "net_worth": compute_net_worth(accounts),
        "liquidity": compute_liquidity(accounts, entries, categories, groups),
        "cashflow_last_3_months": compute_cashflow_series(entries, months_back=3),
    }


def _gather_asset_facts(db: Session, user: User) -> dict:
    assets = db.query(WealthAsset).filter(WealthAsset.user_id == user.id).all()
    return {"assets": compute_asset_performance(assets)}


def _gather_risk_hedging_facts(db: Session, user: User) -> dict:
    accounts = db.query(WealthAccount).filter(WealthAccount.user_id == user.id).all()
    assets = db.query(WealthAsset).filter(WealthAsset.user_id == user.id).all()
    entries = db.query(WealthEntry).filter(WealthEntry.user_id == user.id).all()
    categories = db.query(WealthCategory).filter(WealthCategory.user_id == user.id).all()
    groups = db.query(WealthCategoryGroup).filter(WealthCategoryGroup.user_id == user.id).all()

    return {
        "net_worth": compute_net_worth(accounts, assets),
        "liquidity": compute_liquidity(accounts, entries, categories, groups),
        "diversification": compute_diversification(accounts, assets),
        "asset_performance": compute_asset_performance(assets),
    }


def _gather_diversification_facts(db: Session, user: User) -> dict:
    accounts = db.query(WealthAccount).filter(WealthAccount.user_id == user.id).all()
    assets = db.query(WealthAsset).filter(WealthAsset.user_id == user.id).all()
    return {
        "net_worth": compute_net_worth(accounts, assets),
        "diversification": compute_diversification(accounts, assets),
    }


def _gather_investment_planner_facts(db: Session, user: User) -> dict:
    accounts = db.query(WealthAccount).filter(WealthAccount.user_id == user.id).all()
    assets = db.query(WealthAsset).filter(WealthAsset.user_id == user.id).all()
    entries = db.query(WealthEntry).filter(WealthEntry.user_id == user.id).all()

    cashflow = compute_cashflow_series(entries, months_back=6)
    facts: dict = {
        "net_worth": compute_net_worth(accounts, assets),
        "cashflow_last_6_months": cashflow,
        "income_forecast": compute_income_forecast(entries),
    }

    assumption = (
        db.query(WealthForecastAssumption)
        .filter(WealthForecastAssumption.user_id == user.id, WealthForecastAssumption.is_active.is_(True))
        .first()
    )
    if assumption:
        avg_monthly_net = sum(c["net"] for c in cashflow) / len(cashflow) if cashflow else 0.0
        facts["active_assumption"] = {
            "name": assumption.name,
            "annual_return_rate": assumption.annual_return_rate,
            "years_horizon": assumption.years_horizon,
        }
        facts["net_worth_projection"] = project_net_worth(accounts, assumption, avg_monthly_net, assets)

    return facts


def _gather_goal_planner_facts(db: Session, user: User) -> dict:
    goals = db.query(WealthGoal).filter(WealthGoal.user_id == user.id).all()
    entries = db.query(WealthEntry).filter(WealthEntry.user_id == user.id).all()
    cashflow = compute_cashflow_series(entries, months_back=3)
    avg_monthly_net = sum(c["net"] for c in cashflow) / len(cashflow) if cashflow else 0.0

    return {
        "avg_monthly_net_savings": round(avg_monthly_net, 2),
        "goal_feasibility": compute_goal_feasibility(goals, avg_monthly_net),
    }


def _gather_scenario_strategist_facts(db: Session, user: User) -> dict:
    scenarios = db.query(WealthScenario).filter(WealthScenario.user_id == user.id).all()
    accounts = db.query(WealthAccount).filter(WealthAccount.user_id == user.id).all()
    assets = db.query(WealthAsset).filter(WealthAsset.user_id == user.id).all()
    entries = db.query(WealthEntry).filter(WealthEntry.user_id == user.id).all()

    cashflow = compute_cashflow_series(entries, months_back=3)
    avg_monthly_net = sum(c["net"] for c in cashflow) / len(cashflow) if cashflow else 0.0

    scenario_summaries = []
    for s in scenarios:
        projection = project_scenario(accounts, assets, s, avg_monthly_net)
        final = projection[-1]
        assumed_monthly = s.monthly_contribution_override if s.monthly_contribution_override is not None else round(avg_monthly_net, 2)
        scenario_summaries.append(
            {
                "scenario_id": s.id,
                "name": s.name,
                "scenario_type": s.scenario_type,
                "years_horizon": s.years_horizon,
                "assumed_monthly_contribution": assumed_monthly,
                "final_year_net_worth": final["net_worth"],
                "is_adopted": s.is_adopted,
            }
        )

    return {
        "current_avg_monthly_net_savings": round(avg_monthly_net, 2),
        "scenarios": scenario_summaries,
    }


def _gather_research_advisor_facts(db: Session, user: User) -> dict:
    goals = db.query(WealthGoal).filter(WealthGoal.user_id == user.id).all()
    entries = db.query(WealthEntry).filter(WealthEntry.user_id == user.id).all()
    watchlist = db.query(WealthWatchlistItem).filter(WealthWatchlistItem.user_id == user.id).all()
    topics = db.query(WealthTopic).filter(WealthTopic.user_id == user.id).all()

    cashflow = compute_cashflow_series(entries, months_back=3)
    avg_monthly_net = sum(c["net"] for c in cashflow) / len(cashflow) if cashflow else 0.0

    return {
        "avg_monthly_net_savings": round(avg_monthly_net, 2),
        "goal_feasibility": compute_goal_feasibility(goals, avg_monthly_net),
        "watchlist": [
            {
                "id": w.id,
                "name": w.name,
                "item_type": w.item_type,
                "status": w.status,
                "target_price": w.target_price,
                "current_price": w.current_price,
                "thesis": w.thesis,
                "priority": w.priority,
            }
            for w in watchlist
        ],
        "topics": [
            {
                "id": t.id,
                "title": t.title,
                "description": t.description,
                "category": t.category,
                "status": t.status,
                "related_goal_id": t.related_goal_id,
                "priority": t.priority,
            }
            for t in topics
        ],
    }


def gather_facts(agent_id: str, db: Session, user: User) -> dict:
    if agent_id == "wealth.budget_analyzer":
        return _gather_budget_facts(db, user)
    if agent_id == "wealth.financial_insight_agent":
        return _gather_financial_insight_facts(db, user)
    if agent_id == "wealth.asset_advisor":
        return _gather_asset_facts(db, user)
    if agent_id == "wealth.risk_hedging_agent":
        return _gather_risk_hedging_facts(db, user)
    if agent_id == "wealth.diversification_agent":
        return _gather_diversification_facts(db, user)
    if agent_id == "wealth.investment_planner":
        return _gather_investment_planner_facts(db, user)
    if agent_id == "wealth.goal_planner":
        return _gather_goal_planner_facts(db, user)
    if agent_id == "wealth.scenario_strategist":
        return _gather_scenario_strategist_facts(db, user)
    if agent_id == "wealth.research_advisor":
        return _gather_research_advisor_facts(db, user)
    raise ValueError(f"Unknown agent: {agent_id}")


def run_agent(agent_id: str, db: Session, user: User) -> tuple[str, dict]:
    """Returns (summary_text, facts). Raises ai_provider.AIProviderError on failure."""
    if agent_id not in AGENTS:
        raise ValueError(f"Unknown agent: {agent_id}")

    facts = gather_facts(agent_id, db, user)
    summary = ai_provider.generate(SYSTEM_PROMPT, json.dumps(facts, default=str))
    return summary, facts
