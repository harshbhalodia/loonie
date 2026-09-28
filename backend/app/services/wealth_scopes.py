"""Canonical registry of wealth data "scopes" — the granular categories of a user's own
computed analytics that a marketplace blueprint may request. This is the single source of
truth for what a user is shown and asked to explicitly grant before ANY blueprint (free or
paid, in-house or third-party) receives a byte of their data. A blueprint's declared `inputs`
in its manifest are just a REQUEST; the actual data sent to the model is always the
intersection with what the user has explicitly granted (see services/marketplace_runner.py).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DataScope:
    id: str
    label: str
    description: str


WEALTH_DATA_SCOPES: dict[str, DataScope] = {
    "net_worth": DataScope(
        "net_worth",
        "Net worth",
        "Your total net worth, broken down into liquid, investment, and personal-asset buckets.",
    ),
    "liquidity": DataScope(
        "liquidity",
        "Liquidity & cash buffer",
        "Your liquid balance, essential monthly spending, and how many months of runway you have.",
    ),
    "cashflow": DataScope(
        "cashflow",
        "Cash flow history",
        "Your monthly income, expenses, and net cash flow for recent months.",
    ),
    "diversification": DataScope(
        "diversification",
        "Diversification",
        "How your net worth is spread across account and asset types.",
    ),
    "income_forecast": DataScope(
        "income_forecast",
        "Income forecast",
        "Your historical income trend and a projected forecast.",
    ),
    "goal_feasibility": DataScope(
        "goal_feasibility",
        "Savings goals",
        "Your savings goals, target amounts/dates, and whether you're on track.",
    ),
}


def known_scope_ids() -> set[str]:
    return set(WEALTH_DATA_SCOPES)


def describe(scope_ids: list[str]) -> list[DataScope]:
    """Returns DataScope objects for known ids, silently dropping any unrecognized id (e.g. a
    typo in a blueprint's manifest) — a blueprint can never request access to something outside
    this registry, known or not."""
    return [WEALTH_DATA_SCOPES[s] for s in scope_ids if s in WEALTH_DATA_SCOPES]
