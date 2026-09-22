import uuid
from datetime import datetime, date

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    # 1 = January .. 12 = December; the month a user's financial year starts on, for yearly budgets.
    fiscal_year_start_month: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class WealthAccount(Base):
    __tablename__ = "wealth_accounts"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    type: Mapped[str] = mapped_column(String, nullable=False)
    institution: Mapped[str | None] = mapped_column(String, nullable=True)
    currency: Mapped[str] = mapped_column(String, default="USD")
    opening_balance: Mapped[float] = mapped_column(Float, default=0)
    current_balance: Mapped[float] = mapped_column(Float, default=0)
    is_liquid: Mapped[bool] = mapped_column(Boolean, default=True)
    # "manual": current_balance is user-typed and never touched by entry sync (default, safe for
    # existing accounts that already have entries linked without every real transaction recorded).
    # "computed": current_balance = opening_balance + linked income - linked expense, recalculated
    # on every entry create/update/delete. Only opt in once you're sure ALL cash movements for this
    # account are recorded as entries, or the derived balance will drift from the real balance.
    balance_source: Mapped[str] = mapped_column(String, default="manual", server_default="manual")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class WealthCategoryGroup(Base):
    """User-defined bucket for categories (e.g. Fixed, Variable, Adhoc).

    `is_essential` marks the group's spend as "essential" for the liquidity/runway
    calculation (previously hardcoded to the fixed/variable groups).
    """

    __tablename__ = "wealth_category_groups"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    color: Mapped[str | None] = mapped_column(String, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_essential: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class WealthCategory(Base):
    __tablename__ = "wealth_categories"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    group_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("wealth_category_groups.id", ondelete="SET NULL"), nullable=True
    )
    kind: Mapped[str] = mapped_column(String, nullable=False)
    color: Mapped[str | None] = mapped_column(String, nullable=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    group: Mapped["WealthCategoryGroup | None"] = relationship("WealthCategoryGroup")


class WealthCategoryRule(Base):
    """User-maintained keyword -> category mapping used to auto-categorize statement imports.

    Matching is a case-insensitive substring check against a transaction's description/payee,
    and always takes priority over the AI's own category guess during PDF statement parsing.
    """

    __tablename__ = "wealth_category_rules"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    keyword: Mapped[str] = mapped_column(String, nullable=False)
    category_id: Mapped[str] = mapped_column(String, ForeignKey("wealth_categories.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class WealthEntry(Base):
    __tablename__ = "wealth_entries"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String, nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    entry_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    payee: Mapped[str | None] = mapped_column(String, nullable=True)
    category_id: Mapped[str | None] = mapped_column(String, ForeignKey("wealth_categories.id", ondelete="SET NULL"), nullable=True)
    account_id: Mapped[str | None] = mapped_column(String, ForeignKey("wealth_accounts.id", ondelete="SET NULL"), nullable=True)
    # Links this entry as a contribution towards a goal; goal.current_amount is derived from these.
    goal_id: Mapped[str | None] = mapped_column(String, ForeignKey("wealth_goals.id", ondelete="SET NULL"), nullable=True, index=True)
    is_recurring: Mapped[bool] = mapped_column(Boolean, default=False)
    recurrence_interval: Mapped[str | None] = mapped_column(String, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    import_batch_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class WealthBudget(Base):
    __tablename__ = "wealth_budgets"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    category_id: Mapped[str] = mapped_column(String, ForeignKey("wealth_categories.id", ondelete="CASCADE"))
    # "monthly" resets each calendar month; "yearly" tracks spend across the user's financial year.
    period: Mapped[str] = mapped_column(String, default="monthly")
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    warning_threshold: Mapped[float] = mapped_column(Float, default=80)
    critical_threshold: Mapped[float] = mapped_column(Float, default=100)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class WealthAsset(Base):
    """Physical/personal assets held outside financial accounts (property, vehicle, etc.).

    Contributes `current_value` to net worth's illiquid bucket while `status == "holding"`.
    Selling an asset keeps its history (purchase/sold values) instead of deleting the row.
    """

    __tablename__ = "wealth_assets"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    asset_type: Mapped[str] = mapped_column(String, nullable=False)
    purchase_value: Mapped[float] = mapped_column(Float, nullable=False)
    purchase_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    current_value: Mapped[float] = mapped_column(Float, nullable=False)
    current_value_updated_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String, default="holding")  # holding | sold
    sold_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    sold_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class WealthGoal(Base):
    __tablename__ = "wealth_goals"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    goal_type: Mapped[str] = mapped_column(String, nullable=False)
    target_amount: Mapped[float] = mapped_column(Float, nullable=False)
    # Derived from linked wealth_entries when any exist; otherwise set manually.
    current_amount: Mapped[float] = mapped_column(Float, default=0)
    target_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    achieved_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class WealthScenario(Base):
    """A saved sandbox "what-if" draft — never affects real accounts/assets/entries.

    Projections are computed on demand from the user's current net worth as a starting point,
    but every rate/contribution here is independent of the single "active" WealthForecastAssumption
    used for the main Analytics projection, so a user can draft as many drafts as they like.
    """

    __tablename__ = "wealth_scenarios"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # "custom" | "best_case" | "expected_case" | "worst_case" — a label only, the rates below drive the math.
    scenario_type: Mapped[str] = mapped_column(String, default="custom")
    years_horizon: Mapped[int] = mapped_column(Integer, default=10)
    investment_return_rate: Mapped[float] = mapped_column(Float, default=0.07)
    personal_asset_growth_rate: Mapped[float] = mapped_column(Float, default=0.02)
    # If None, falls back to the user's actual trailing avg monthly net cashflow at run time.
    monthly_contribution_override: Mapped[float | None] = mapped_column(Float, nullable=True)
    income_growth_rate: Mapped[float] = mapped_column(Float, default=0.0)
    # Bookmark for "this is the plan I'm going with" — bookkeeping only, never mutates real data.
    is_adopted: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    account_configs: Mapped[list["WealthScenarioAccountConfig"]] = relationship(
        "WealthScenarioAccountConfig", cascade="all, delete-orphan", passive_deletes=True
    )
    asset_configs: Mapped[list["WealthScenarioAssetConfig"]] = relationship(
        "WealthScenarioAssetConfig", cascade="all, delete-orphan", passive_deletes=True
    )
    income_sources: Mapped[list["WealthScenarioIncomeSource"]] = relationship(
        "WealthScenarioIncomeSource", cascade="all, delete-orphan", passive_deletes=True
    )


class WealthScenarioAccountConfig(Base):
    """Per-account growth override within one scenario draft — lets a scenario model that not
    every account grows (e.g. a checking account stays flat while an investment account
    compounds). Replaced wholesale on every scenario save, like a draft's own config blob."""

    __tablename__ = "wealth_scenario_account_configs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    scenario_id: Mapped[str] = mapped_column(String, ForeignKey("wealth_scenarios.id", ondelete="CASCADE"), index=True)
    account_id: Mapped[str] = mapped_column(String, ForeignKey("wealth_accounts.id", ondelete="CASCADE"))
    # None = fall back to the scenario's default rate for this account's type (0% unless investment/retirement).
    growth_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    include_in_growth: Mapped[bool] = mapped_column(Boolean, default=True)


class WealthScenarioAssetConfig(Base):
    """Per-asset growth override within one scenario draft (e.g. a car depreciates while a home
    appreciates) — overrides the scenario's blanket personal_asset_growth_rate for one asset."""

    __tablename__ = "wealth_scenario_asset_configs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    scenario_id: Mapped[str] = mapped_column(String, ForeignKey("wealth_scenarios.id", ondelete="CASCADE"), index=True)
    asset_id: Mapped[str] = mapped_column(String, ForeignKey("wealth_assets.id", ondelete="CASCADE"))
    growth_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    include_in_growth: Mapped[bool] = mapped_column(Boolean, default=True)


class WealthScenarioIncomeSource(Base):
    """An extra income stream modeled only within one scenario draft (raise, side hustle, rental
    income, etc.) — on top of the scenario's base monthly contribution, with its own growth rate."""

    __tablename__ = "wealth_scenario_income_sources"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    scenario_id: Mapped[str] = mapped_column(String, ForeignKey("wealth_scenarios.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    monthly_amount: Mapped[float] = mapped_column(Float, nullable=False)
    growth_rate: Mapped[float] = mapped_column(Float, default=0.0)


class WealthWatchlistItem(Base):
    """An investment idea being tracked/considered — stock, fund, crypto, property, product, etc.
    Purely informational: never counted in net worth until the user actually buys it (at which
    point it becomes a real WealthAccount/WealthAsset/WealthEntry)."""

    __tablename__ = "wealth_watchlist_items"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    item_type: Mapped[str] = mapped_column(String, nullable=False)  # stock|etf|fund|crypto|real_estate|product|other
    symbol: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, default="watching")  # watching|researching|decided_in|decided_out
    target_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    current_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str] = mapped_column(String, default="USD")
    thesis: Mapped[str | None] = mapped_column(Text, nullable=True)
    url: Mapped[str | None] = mapped_column(String, nullable=True)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class WealthTopic(Base):
    """A research topic/knowledge note the user cares about (e.g. "index fund investing",
    "real estate in X market") — curated context fed to the research advisor agent, distinct from
    watchlist items which are specific tradeable instruments rather than open-ended topics."""

    __tablename__ = "wealth_topics"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, default="exploring")  # exploring|researching|decided|parked
    related_goal_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("wealth_goals.id", ondelete="SET NULL"), nullable=True
    )
    priority: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class WealthForecastAssumption(Base):
    __tablename__ = "wealth_forecast_assumptions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    annual_return_rate: Mapped[float] = mapped_column(Float, default=0.07)
    inflation_rate: Mapped[float] = mapped_column(Float, default=0.03)
    years_horizon: Mapped[int] = mapped_column(Integer, default=10)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class WealthInsight(Base):
    """Agent-produced output. Kept separate from raw data so agents never write to core tables."""

    __tablename__ = "wealth_insights"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    agent_id: Mapped[str] = mapped_column(String, nullable=False)
    severity: Mapped[str] = mapped_column(String, default="info")  # info | warning | critical
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    facts_json: Mapped[str] = mapped_column(Text, nullable=False)  # computed facts the agent was given
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AgentExecutionLog(Base):
    __tablename__ = "agent_execution_logs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    agent_id: Mapped[str] = mapped_column(String, nullable=False)
    agent_version: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)  # ok | error
    input_ref: Mapped[str] = mapped_column(Text, nullable=False)
    output: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class WealthStatementImport(Base):
    """One uploaded statement file (CSV or PDF) for a single account.

    Transactions are parsed and held in `transactions_json` for review before the user applies
    them; applying upserts wealth_entries (matched by account+date+amount+normalized payee, else
    inserted) so re-uploading the same statement updates existing rows and only adds what's
    missing, instead of duplicating. `statement_balance`/`due_date`/`minimum_due` are populated
    only for credit_card accounts — purely informational, never fed into net worth/analytics.
    """

    __tablename__ = "wealth_statement_imports"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    account_id: Mapped[str] = mapped_column(String, ForeignKey("wealth_accounts.id", ondelete="CASCADE"), index=True)
    file_name: Mapped[str] = mapped_column(String, nullable=False)
    stored_path: Mapped[str | None] = mapped_column(String, nullable=True)
    source_type: Mapped[str] = mapped_column(String, nullable=False)  # csv | pdf
    # queued -> processing -> parsed -> applied ; error on failure at any step
    status: Mapped[str] = mapped_column(String, default="queued")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    transactions_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    statement_period: Mapped[str | None] = mapped_column(String, nullable=True)
    transaction_count: Mapped[int] = mapped_column(Integer, default=0)
    inserted_count: Mapped[int] = mapped_column(Integer, default=0)
    updated_count: Mapped[int] = mapped_column(Integer, default=0)
    statement_balance: Mapped[float | None] = mapped_column(Float, nullable=True)
    minimum_due: Mapped[float | None] = mapped_column(Float, nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    paid: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class WealthKeywordCandidate(Base):
    """A candidate keyword -> category rule awaiting user review.

    Auto-flagged the moment an applied statement transaction lands with no category; refined by
    the `wealth.keyword_learner` agent, which only fills in `suggested_category_id` as a proposal.
    Nothing here ever becomes a real rule until the user explicitly approves it.
    """

    __tablename__ = "wealth_keyword_candidates"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    keyword: Mapped[str] = mapped_column(String, nullable=False)
    sample_payee: Mapped[str | None] = mapped_column(String, nullable=True)
    occurrence_count: Mapped[int] = mapped_column(Integer, default=1)
    suggested_category_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("wealth_categories.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String, default="pending")  # pending | approved | rejected
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class WealthReminder(Base):
    """Recurring reminder to upload/reconcile one account's statement, so records stay current.
    `next_due_date` is recomputed from `frequency` whenever a statement is applied for the account."""

    __tablename__ = "wealth_reminders"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    account_id: Mapped[str] = mapped_column(String, ForeignKey("wealth_accounts.id", ondelete="CASCADE"), index=True)
    # weekly | biweekly | semi_monthly | monthly | quarterly | yearly
    frequency: Mapped[str] = mapped_column(String, nullable=False)
    next_due_date: Mapped[date] = mapped_column(Date, nullable=False)
    last_completed_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class WealthJob(Base):
    """One queued unit of work (a statement parse, currently) processed strictly one-at-a-time by
    a single background worker — guarantees the local AI endpoint never receives overlapping
    requests and every request is independent, with no shared/cached context between jobs."""

    __tablename__ = "wealth_jobs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    job_type: Mapped[str] = mapped_column(String, nullable=False)  # statement_parse
    status: Mapped[str] = mapped_column(String, default="queued")  # queued | processing | done | error
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    result_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class WealthBudgetHistory(Base):
    """Snapshot of a budget's amount/thresholds right before they changed.

    `effective_from` is the date the change happened — this snapshot's values were in effect for
    any period strictly before that date. Historical month/quarter/year rollups look up the first
    snapshot whose `effective_from` is after the period being evaluated (falling back to the
    budget's current live values if the budget was never changed, or not changed since).
    """

    __tablename__ = "wealth_budget_history"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    budget_id: Mapped[str] = mapped_column(String, ForeignKey("wealth_budgets.id", ondelete="CASCADE"), index=True)
    category_id: Mapped[str] = mapped_column(String, ForeignKey("wealth_categories.id", ondelete="CASCADE"))
    period: Mapped[str] = mapped_column(String, nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    warning_threshold: Mapped[float] = mapped_column(Float, nullable=False)
    critical_threshold: Mapped[float] = mapped_column(Float, nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class DecisionRecord(Base):
    """One decision run through Jev (TypeSafe's System One Choice model), plus the chosen option
    and the profile snapshot it was grounded in — kept as history so past decisions and the
    situation behind them stay reviewable later."""

    __tablename__ = "decisions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    # set when this decision was generated by an auto-mode run rather than the manual form.
    session_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("decision_auto_sessions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    round_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    options_json: Mapped[str] = mapped_column(Text, nullable=False)  # [{"name": ..., "description": ...}]
    chosen_option: Mapped[str | None] = mapped_column(String, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    probabilities_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    profile_snapshot_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String, default="ok")  # ok | error
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class DecisionContext(Base):
    """Freeform running summary of past decisions for the Decision Maker — one row per user,
    manually editable, and (re)drafted by the local AI model at the start of each auto-mode run."""

    __tablename__ = "decision_context"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True)
    content: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class DecisionPlan(Base):
    """Freeform summary of the user's goals/budget/high-level plan — same one-row-per-user editing
    model as DecisionContext, given to Jev/the local model as extra grounding context."""

    __tablename__ = "decision_plan"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True)
    content: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class DecisionAutoSession(Base):
    """One 'auto mode' run: a loop of Jev-evaluated decisions grounded in the same plan brief,
    advanced one explicit round at a time by the frontend until the user stops it (or the model
    says there's nothing further to decide) — there is no server-side background loop."""

    __tablename__ = "decision_auto_sessions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    plan_brief: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String, default="running")  # running | stopped | done
    rounds_completed: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

