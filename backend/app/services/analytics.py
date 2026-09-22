"""Deterministic financial calculations for the Wealth blueprint.

No LLM involvement here — agents only explain numbers computed by this module.
Ported 1:1 from the frontend's former analytics.ts so the backend is the single
source of truth for all financial math.
"""
from __future__ import annotations

from calendar import monthrange
from collections import defaultdict
from datetime import date, timedelta

from app.models import (
    WealthAccount,
    WealthAsset,
    WealthBudget,
    WealthBudgetHistory,
    WealthCategory,
    WealthCategoryGroup,
    WealthEntry,
    WealthForecastAssumption,
    WealthGoal,
    WealthScenario,
)

# Day-to-day spend cards — tracked (statements, amount due) but never counted in wealth calcs.
CREDIT_CARD_ACCOUNT_TYPE = "credit_card"


def _exclude_credit_cards(accounts: list[WealthAccount]) -> list[WealthAccount]:
    return [a for a in accounts if a.type != CREDIT_CARD_ACCOUNT_TYPE]


def _round2(value: float) -> float:
    return round(value, 2)


def _month_key(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def _month_label(d: date) -> str:
    return d.strftime("%b")


def fiscal_year_window(fiscal_year_start_month: int, reference_date: date) -> tuple[date, date]:
    """Returns (start, end) inclusive dates of the financial year containing reference_date,
    given the month (1-12) the user's financial year starts on."""
    start_year = reference_date.year if reference_date.month >= fiscal_year_start_month else reference_date.year - 1
    start = date(start_year, fiscal_year_start_month, 1)
    end = date(start_year + 1, fiscal_year_start_month, 1) - timedelta(days=1)
    return start, end


def compute_net_worth(accounts: list[WealthAccount], assets: list[WealthAsset] | None = None) -> dict:
    accounts = _exclude_credit_cards(accounts)
    liquid = 0.0
    illiquid = 0.0
    investments = 0.0

    for acc in accounts:
        balance = -abs(acc.current_balance) if acc.type in ("credit", "loan") else acc.current_balance
        if acc.type in ("investment", "retirement"):
            investments += balance
        if acc.is_liquid:
            liquid += balance
        else:
            illiquid += balance

    # Held physical assets (home, car, ...) count as illiquid net worth; sold ones are excluded.
    personal_assets = 0.0
    for asset in assets or []:
        if asset.status == "holding":
            personal_assets += asset.current_value
            illiquid += asset.current_value

    return {
        "total": _round2(liquid + illiquid),
        "liquid": _round2(liquid),
        "illiquid": _round2(illiquid),
        "investments": _round2(investments),
        "personal_assets": _round2(personal_assets),
    }


def compute_cashflow_series(entries: list[WealthEntry], months_back: int = 12, today: date | None = None) -> list[dict]:
    today = today or date.today()
    buckets: dict[str, dict[str, float]] = {}
    order: list[tuple[str, date]] = []

    for i in range(months_back - 1, -1, -1):
        month_index = today.month - 1 - i
        year = today.year + month_index // 12
        month = month_index % 12 + 1
        bucket_date = date(year, month, 1)
        key = _month_key(bucket_date)
        buckets[key] = {"incoming": 0.0, "outgoing": 0.0}
        order.append((key, bucket_date))

    for entry in entries:
        key = _month_key(entry.entry_date)
        if key not in buckets:
            continue
        if entry.type == "income":
            buckets[key]["incoming"] += entry.amount
        else:
            buckets[key]["outgoing"] += entry.amount

    return [
        {
            "month": key,
            "label": _month_label(d),
            "incoming": _round2(buckets[key]["incoming"]),
            "outgoing": _round2(buckets[key]["outgoing"]),
            "net": _round2(buckets[key]["incoming"] - buckets[key]["outgoing"]),
        }
        for key, d in order
    ]


def compute_category_group_breakdown(
    entries: list[WealthEntry], categories: list[WealthCategory], groups: list[WealthCategoryGroup], month: str | None = None
) -> list[dict]:
    category_by_id = {c.id: c for c in categories}
    group_by_id = {g.id: g for g in groups}
    totals: dict[str | None, float] = defaultdict(float)

    for entry in entries:
        if entry.type != "expense":
            continue
        if month and _month_key(entry.entry_date) != month:
            continue
        category = category_by_id.get(entry.category_id) if entry.category_id else None
        group_id = category.group_id if category else None
        totals[group_id] += entry.amount

    results = []
    for group_id, total in totals.items():
        group = group_by_id.get(group_id) if group_id else None
        results.append(
            {
                "group_id": group_id,
                "group_name": group.name if group else "Uncategorized",
                "color": group.color if group else None,
                "total": _round2(total),
            }
        )
    return sorted(results, key=lambda x: x["total"], reverse=True)


def compute_budget_statuses(
    budgets: list[WealthBudget],
    entries: list[WealthEntry],
    categories: list[WealthCategory],
    fiscal_year_start_month: int = 1,
    reference_date: date | None = None,
) -> list[dict]:
    reference_date = reference_date or date.today()
    category_by_id = {c.id: c for c in categories}
    month = _month_key(reference_date)
    day_of_month = reference_date.day
    days_in_month = monthrange(reference_date.year, reference_date.month)[1]
    fy_start, fy_end = fiscal_year_window(fiscal_year_start_month, reference_date)

    results = []
    for budget in budgets:
        if budget.period == "yearly":
            spent = sum(
                e.amount
                for e in entries
                if e.type == "expense" and e.category_id == budget.category_id and fy_start <= e.entry_date <= fy_end
            )
            days_elapsed = (reference_date - fy_start).days + 1
            days_total = (fy_end - fy_start).days + 1
            projected = (spent / days_elapsed * days_total) if days_elapsed > 0 else spent
        else:
            spent = sum(
                e.amount
                for e in entries
                if e.type == "expense" and e.category_id == budget.category_id and _month_key(e.entry_date) == month
            )
            projected = (spent / day_of_month * days_in_month) if day_of_month > 0 else spent

        percent = (spent / budget.amount * 100) if budget.amount > 0 else 0.0

        status = "ok"
        if percent >= budget.critical_threshold:
            status = "critical"
        elif percent >= budget.warning_threshold:
            status = "warning"

        category = category_by_id.get(budget.category_id)
        results.append(
            {
                "budget_id": budget.id,
                "category_id": budget.category_id,
                "category_name": category.name if category else "Uncategorized",
                "period": budget.period,
                "amount": budget.amount,
                "spent": _round2(spent),
                "percent": _round2(percent),
                "status": status,
                "projected_period_end": _round2(projected),
            }
        )
    return results


def _period_bounds(granularity: str, offset: int, today: date) -> tuple[date, date, str, str]:
    """Returns (start, end, period_key, period_label) for one period, where offset=0 is the
    period containing `today` and offset=1 is the previous one, etc."""
    if granularity == "month":
        month_index = today.month - 1 - offset
        year = today.year + month_index // 12
        month = month_index % 12 + 1
        start = date(year, month, 1)
        end = date(year, month, monthrange(year, month)[1])
        return start, end, f"{year:04d}-{month:02d}", start.strftime("%b %Y")

    if granularity == "quarter":
        total_quarters = today.year * 4 + (today.month - 1) // 3 - offset
        year, q = divmod(total_quarters, 4)
        start_month = q * 3 + 1
        start = date(year, start_month, 1)
        end_month = start_month + 2
        end = date(year, end_month, monthrange(year, end_month)[1])
        return start, end, f"{year:04d}-Q{q + 1}", f"Q{q + 1} {year}"

    if granularity == "year":
        year = today.year - offset
        return date(year, 1, 1), date(year, 12, 31), f"{year:04d}", str(year)

    raise ValueError(f"Unknown granularity: {granularity}")


def compute_budget_history(
    budgets: list[WealthBudget],
    histories: list[WealthBudgetHistory],
    entries: list[WealthEntry],
    categories: list[WealthCategory],
    granularity: str = "month",
    periods_back: int = 12,
    today: date | None = None,
) -> list[dict]:
    """Month/quarter/year rollup of actual spend vs. the budget amount that was effective during
    each historical period (not necessarily today's current amount — see WealthBudgetHistory)."""
    today = today or date.today()
    category_by_id = {c.id: c for c in categories}

    histories_by_budget: dict[str, list[WealthBudgetHistory]] = defaultdict(list)
    for h in histories:
        histories_by_budget[h.budget_id].append(h)
    for snapshots in histories_by_budget.values():
        snapshots.sort(key=lambda h: h.effective_from)

    def _amount_at(budget: WealthBudget, as_of: date) -> tuple[float, float, float]:
        for snapshot in histories_by_budget.get(budget.id, []):
            if as_of < snapshot.effective_from:
                return snapshot.amount, snapshot.warning_threshold, snapshot.critical_threshold
        return budget.amount, budget.warning_threshold, budget.critical_threshold

    results = []
    for offset in range(periods_back - 1, -1, -1):
        start, end, period_key, period_label = _period_bounds(granularity, offset, today)
        for budget in budgets:
            amount, warning_threshold, critical_threshold = _amount_at(budget, end)
            spent = sum(
                e.amount
                for e in entries
                if e.type == "expense" and e.category_id == budget.category_id and start <= e.entry_date <= end
            )
            percent = (spent / amount * 100) if amount > 0 else 0.0
            status = "ok"
            if percent >= critical_threshold:
                status = "critical"
            elif percent >= warning_threshold:
                status = "warning"

            category = category_by_id.get(budget.category_id)
            results.append(
                {
                    "period_key": period_key,
                    "period_label": period_label,
                    "budget_id": budget.id,
                    "category_id": budget.category_id,
                    "category_name": category.name if category else "Uncategorized",
                    "amount": _round2(amount),
                    "spent": _round2(spent),
                    "percent": _round2(percent),
                    "status": status,
                }
            )
    return results


def compute_liquidity(
    accounts: list[WealthAccount],
    entries: list[WealthEntry],
    categories: list[WealthCategory],
    groups: list[WealthCategoryGroup],
    months_back: int = 3,
    today: date | None = None,
) -> dict:
    today = today or date.today()
    net_worth = compute_net_worth(accounts)
    category_by_id = {c.id: c for c in categories}
    group_by_id = {g.id: g for g in groups}

    month_index = today.month - 1 - months_back
    year = today.year + month_index // 12
    month = month_index % 12 + 1
    cutoff = date(year, month, 1)

    essential_total = 0.0
    months_seen: set[str] = set()

    for entry in entries:
        if entry.type != "expense":
            continue
        if entry.entry_date < cutoff:
            continue
        category = category_by_id.get(entry.category_id) if entry.category_id else None
        group = group_by_id.get(category.group_id) if category and category.group_id else None
        if group and group.is_essential:
            essential_total += entry.amount
            months_seen.add(_month_key(entry.entry_date))

    divisor = max(len(months_seen), 1)
    avg_monthly = _round2(essential_total / divisor)

    return {
        "liquid_balance": net_worth["liquid"],
        "avg_monthly_essential_spend": avg_monthly,
        "months_of_runway": _round2(net_worth["liquid"] / avg_monthly) if avg_monthly > 0 else None,
    }


def project_net_worth(
    accounts: list[WealthAccount],
    assumption: WealthForecastAssumption,
    monthly_net_contribution: float,
    assets: list[WealthAsset] | None = None,
    today: date | None = None,
) -> list[dict]:
    today = today or date.today()
    net_worth = compute_net_worth(accounts, assets)
    annual_contribution = monthly_net_contribution * 12
    rate = assumption.annual_return_rate

    investments = net_worth["investments"]
    liquid = net_worth["liquid"] - net_worth["investments"]
    illiquid = net_worth["illiquid"]

    points = [
        {
            "year": today.year,
            "liquid": _round2(liquid),
            "investments": _round2(investments),
            "illiquid": _round2(illiquid),
            "net_worth": _round2(liquid + investments + illiquid),
        }
    ]

    for i in range(1, assumption.years_horizon + 1):
        investments = investments * (1 + rate) + max(annual_contribution, 0)
        points.append(
            {
                "year": today.year + i,
                "liquid": _round2(liquid),
                "investments": _round2(investments),
                "illiquid": _round2(illiquid),
                "net_worth": _round2(liquid + investments + illiquid),
            }
        )

    return points


def compute_asset_performance(assets: list[WealthAsset], today: date | None = None) -> list[dict]:
    """Deterministic gain/loss facts per asset, handed to the asset advisor agent to interpret
    (the agent only explains these numbers — it never decides or invents a hold/sell verdict itself)."""
    today = today or date.today()
    results = []
    for asset in assets:
        reference_value = asset.sold_value if asset.status == "sold" and asset.sold_value is not None else asset.current_value
        gain_loss = reference_value - asset.purchase_value
        gain_loss_percent = _round2(gain_loss / asset.purchase_value * 100) if asset.purchase_value > 0 else None
        end_date = asset.sold_date if asset.status == "sold" and asset.sold_date else today
        holding_period_days = (end_date - asset.purchase_date).days if asset.purchase_date else None
        results.append(
            {
                "asset_id": asset.id,
                "name": asset.name,
                "asset_type": asset.asset_type,
                "status": asset.status,
                "purchase_value": asset.purchase_value,
                "current_value": _round2(reference_value),
                "gain_loss": _round2(gain_loss),
                "gain_loss_percent": gain_loss_percent,
                "holding_period_days": holding_period_days,
            }
        )
    return results


def _recurring_monthly_amount(entry: WealthEntry) -> float:
    """Normalizes a recurring entry's amount to an equivalent monthly figure."""
    if entry.recurrence_interval == "yearly":
        return entry.amount / 12
    if entry.recurrence_interval == "weekly":
        return entry.amount * 52 / 12
    if entry.recurrence_interval == "biweekly":
        return entry.amount * 26 / 12
    return entry.amount  # "monthly" or unspecified recurrence


def compute_income_forecast(
    entries: list[WealthEntry], months_back: int = 6, months_forward: int = 6, today: date | None = None
) -> dict:
    """Projects future monthly income from trailing actuals plus known recurring income.

    Deterministic only: history is a straight sum of past income entries per month, the
    forecast trend is an ordinary-least-squares slope over that history, and the projection
    is floored at the known recurring monthly income so a quiet month never forecasts below
    committed/recurring income. The agent layer only explains this, never recomputes it.
    """
    today = today or date.today()
    history: list[dict] = []

    for i in range(months_back - 1, -1, -1):
        month_index = today.month - 1 - i
        year = today.year + month_index // 12
        month = month_index % 12 + 1
        bucket_date = date(year, month, 1)
        key = _month_key(bucket_date)
        total = sum(e.amount for e in entries if e.type == "income" and _month_key(e.entry_date) == key)
        history.append({"month": key, "label": _month_label(bucket_date), "income": _round2(total)})

    values = [h["income"] for h in history]
    n = len(values)
    avg_monthly_income = _round2(sum(values) / n) if n else 0.0

    slope = 0.0
    if n >= 2:
        mean_x = (n - 1) / 2
        mean_y = sum(values) / n
        denominator = sum((i - mean_x) ** 2 for i in range(n))
        if denominator:
            slope = sum((i - mean_x) * (values[i] - mean_y) for i in range(n)) / denominator

    recurring_monthly_income = _round2(
        sum(_recurring_monthly_amount(e) for e in entries if e.type == "income" and e.is_recurring)
    )

    forecast: list[dict] = []
    for i in range(1, months_forward + 1):
        month_index = today.month - 1 + i
        year = today.year + month_index // 12
        month = month_index % 12 + 1
        bucket_date = date(year, month, 1)
        projected = max(avg_monthly_income + slope * (n - 1 + i), recurring_monthly_income)
        forecast.append({"month": _month_key(bucket_date), "label": _month_label(bucket_date), "income": _round2(projected)})

    return {
        "history": history,
        "forecast": forecast,
        "avg_monthly_income": avg_monthly_income,
        "recurring_monthly_income": recurring_monthly_income,
        "trend_monthly_change": _round2(slope),
    }


def compute_diversification(accounts: list[WealthAccount], assets: list[WealthAsset] | None = None) -> dict:
    """Breaks net worth down by account/asset type to surface concentration risk.

    Only positive-balance buckets count toward allocation percentages — a credit card or loan
    is a liability, not a diversification slice.
    """
    accounts = _exclude_credit_cards(accounts)
    buckets: dict[str, float] = defaultdict(float)

    for acc in accounts:
        balance = -abs(acc.current_balance) if acc.type in ("credit", "loan") else acc.current_balance
        if balance > 0:
            buckets[acc.type] += balance

    for asset in assets or []:
        if asset.status == "holding" and asset.current_value > 0:
            buckets[f"asset:{asset.asset_type}"] += asset.current_value

    total = sum(buckets.values())
    allocations = [
        {
            "label": label,
            "amount": _round2(amount),
            "percent": _round2(amount / total * 100) if total > 0 else 0.0,
        }
        for label, amount in buckets.items()
    ]
    allocations.sort(key=lambda x: x["amount"], reverse=True)
    largest = allocations[0] if allocations else None

    return {
        "allocations": allocations,
        "total_allocatable": _round2(total),
        "largest_holding_label": largest["label"] if largest else None,
        "concentration_percent": largest["percent"] if largest else 0.0,
    }


def compute_goal_feasibility(
    goals: list[WealthGoal], avg_monthly_net_savings: float, today: date | None = None
) -> list[dict]:
    """Compares each open goal's required monthly contribution against the actual savings rate.

    `status` is a deterministic threshold check (required vs. avg_monthly_net_savings) — the
    goal-planner agent only explains this verdict, it never invents its own feasibility call.
    """
    today = today or date.today()
    results = []

    for g in goals:
        if g.achieved_at is not None:
            continue

        remaining = max(g.target_amount - g.current_amount, 0.0)
        months_remaining: int | None = None
        required_monthly: float | None = None

        if g.target_date:
            months_remaining = max((g.target_date.year - today.year) * 12 + (g.target_date.month - today.month), 1)
            required_monthly = _round2(remaining / months_remaining)

        if required_monthly is None:
            status = "no_target_date"
        elif avg_monthly_net_savings <= 0:
            status = "off_track"
        elif required_monthly <= avg_monthly_net_savings:
            status = "on_track"
        elif required_monthly <= avg_monthly_net_savings * 1.5:
            status = "at_risk"
        else:
            status = "off_track"

        results.append(
            {
                "goal_id": g.id,
                "name": g.name,
                "goal_type": g.goal_type,
                "target_amount": g.target_amount,
                "current_amount": g.current_amount,
                "remaining_amount": _round2(remaining),
                "target_date": g.target_date,
                "months_remaining": months_remaining,
                "required_monthly_contribution": required_monthly,
                "status": status,
            }
        )
    return results


def project_scenario(
    accounts: list[WealthAccount],
    assets: list[WealthAsset],
    scenario: WealthScenario,
    avg_monthly_net_contribution: float,
    today: date | None = None,
) -> list[dict]:
    """Sandbox what-if projection for a single saved draft scenario.

    Reads current accounts/assets ONLY as a starting snapshot — this never writes back to them,
    so drafting (and deleting) any number of scenarios never touches real data. Unlike the single
    "active" WealthForecastAssumption used on the Analytics page, each scenario independently
    overrides the investment return rate, personal-asset appreciation rate, and monthly
    contribution (with its own growth rate), so best-case/worst-case/custom drafts don't collide.

    Growth is modeled per-account and per-asset (not one blanket rate) because not every account
    or asset actually generates returns: an account/asset only grows at `investment_return_rate` /
    `personal_asset_growth_rate` by default if it's an investment/retirement account (accounts) or
    always (assets) — every other account defaults to flat (0%) unless the scenario's
    `account_configs`/`asset_configs` explicitly override its rate (and can even turn its growth
    off entirely via `include_in_growth=False`, e.g. modeling a car depreciating at a set rate
    while a checking account never grows). Extra `income_sources` layer additional contributions
    (each with their own growth rate) on top of the base monthly contribution.
    """
    today = today or date.today()
    accounts = _exclude_credit_cards(accounts)

    account_config_by_id = {c.account_id: c for c in scenario.account_configs}
    asset_config_by_id = {c.asset_id: c for c in scenario.asset_configs}

    def _account_rate(acc: WealthAccount) -> float:
        cfg = account_config_by_id.get(acc.id)
        if cfg and not cfg.include_in_growth:
            return 0.0
        if cfg and cfg.growth_rate is not None:
            return cfg.growth_rate
        return scenario.investment_return_rate if acc.type in ("investment", "retirement") else 0.0

    def _asset_rate(asset: WealthAsset) -> float:
        cfg = asset_config_by_id.get(asset.id)
        if cfg and not cfg.include_in_growth:
            return 0.0
        if cfg and cfg.growth_rate is not None:
            return cfg.growth_rate
        return scenario.personal_asset_growth_rate

    # Starting balances, signed the same way compute_net_worth treats credit/loan as debt.
    account_balances: dict[str, float] = {}
    account_bucket: dict[str, str] = {}
    for acc in accounts:
        balance = -abs(acc.current_balance) if acc.type in ("credit", "loan") else acc.current_balance
        account_balances[acc.id] = balance
        if acc.type in ("investment", "retirement"):
            account_bucket[acc.id] = "investments"
        elif acc.is_liquid:
            account_bucket[acc.id] = "liquid"
        else:
            account_bucket[acc.id] = "illiquid_other"

    asset_values: dict[str, float] = {a.id: a.current_value for a in assets if a.status == "holding"}

    base_monthly = (
        scenario.monthly_contribution_override
        if scenario.monthly_contribution_override is not None
        else avg_monthly_net_contribution
    )
    income_sources = [{"monthly_amount": s.monthly_amount, "growth_rate": s.growth_rate} for s in scenario.income_sources]

    # New contributions grow whichever investment/retirement accounts are still opted into growth;
    # with none, they sit in an unallocated pool that still compounds at the scenario's default rate.
    eligible_account_ids = [
        acc.id
        for acc in accounts
        if account_bucket[acc.id] == "investments"
        and (account_config_by_id.get(acc.id) is None or account_config_by_id[acc.id].include_in_growth)
    ]
    unallocated_pool = 0.0

    def _bucket_totals() -> dict[str, float]:
        totals = {"liquid": 0.0, "investments": 0.0, "illiquid_other": 0.0}
        for acc_id, bal in account_balances.items():
            totals[account_bucket[acc_id]] += bal
        totals["investments"] += unallocated_pool
        return {
            "liquid": totals["liquid"],
            "investments": totals["investments"],
            "personal_assets": sum(asset_values.values()),
            "illiquid_other": totals["illiquid_other"],
        }

    def _point(year: int) -> dict:
        totals = _bucket_totals()
        return {
            "year": year,
            "liquid": _round2(totals["liquid"]),
            "investments": _round2(totals["investments"]),
            "personal_assets": _round2(totals["personal_assets"]),
            "illiquid_other": _round2(totals["illiquid_other"]),
            "net_worth": _round2(sum(totals.values())),
        }

    points = [_point(today.year)]

    for i in range(1, scenario.years_horizon + 1):
        for acc in accounts:
            account_balances[acc.id] *= 1 + _account_rate(acc)
        for asset in assets:
            if asset.id in asset_values:
                asset_values[asset.id] *= 1 + _asset_rate(asset)

        year_base_monthly = base_monthly * ((1 + scenario.income_growth_rate) ** (i - 1))
        year_extra_monthly = sum(src["monthly_amount"] * ((1 + src["growth_rate"]) ** (i - 1)) for src in income_sources)
        annual_contribution = max((year_base_monthly + year_extra_monthly) * 12, 0)

        if eligible_account_ids:
            weights = {acc_id: max(account_balances[acc_id], 0) for acc_id in eligible_account_ids}
            weight_total = sum(weights.values())
            if weight_total <= 0:
                share = annual_contribution / len(eligible_account_ids)
                for acc_id in eligible_account_ids:
                    account_balances[acc_id] += share
            else:
                for acc_id in eligible_account_ids:
                    account_balances[acc_id] += annual_contribution * (weights[acc_id] / weight_total)
        else:
            unallocated_pool = unallocated_pool * (1 + scenario.investment_return_rate) + annual_contribution

        points.append(_point(today.year + i))

    return points
