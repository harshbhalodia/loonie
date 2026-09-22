from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

EntryType = Literal["income", "expense"]
RecurrenceInterval = Literal["weekly", "biweekly", "monthly", "yearly"] | None
# "credit_card" is a day-to-day spend card, fully excluded from net worth/analytics (see
# analytics.py); "credit" remains a real liability (e.g. a carried revolving balance/HELOC).
AccountType = Literal["checking", "savings", "credit", "credit_card", "investment", "retirement", "loan", "other"]
BalanceSource = Literal["manual", "computed"]
ReminderFrequency = Literal["weekly", "biweekly", "semi_monthly", "monthly", "quarterly", "yearly"]
StatementImportStatus = Literal["queued", "processing", "parsed", "applied", "error"]
KeywordCandidateStatus = Literal["pending", "approved", "rejected"]
JobStatus = Literal["queued", "processing", "done", "error"]
BudgetHistoryGranularity = Literal["month", "quarter", "year"]
GoalType = Literal["emergency_fund", "savings", "debt_repayment", "investment", "major_purchase", "other"]
BudgetPeriod = Literal["monthly", "yearly"]
AssetType = Literal["property", "vehicle", "jewelry", "collectible", "other"]
AssetStatus = Literal["holding", "sold"]
WatchlistItemType = Literal["stock", "etf", "fund", "crypto", "real_estate", "product", "other"]
WatchlistStatus = Literal["watching", "researching", "decided_in", "decided_out"]
TopicStatus = Literal["exploring", "researching", "decided", "parked"]


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------------- auth ----------------


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(ORMModel):
    id: str
    email: str
    fiscal_year_start_month: int
    created_at: datetime


class UserSettingsIn(BaseModel):
    fiscal_year_start_month: int = Field(ge=1, le=12)


# ---------------- accounts ----------------


class AccountIn(BaseModel):
    id: str | None = None
    name: str
    type: AccountType
    institution: str | None = None
    currency: str = "USD"
    opening_balance: float = 0
    current_balance: float = 0
    is_liquid: bool = True
    balance_source: BalanceSource = "manual"


class AccountOut(ORMModel):
    id: str
    name: str
    type: str
    institution: str | None
    currency: str
    opening_balance: float
    current_balance: float
    is_liquid: bool
    balance_source: str
    created_at: datetime


# ---------------- assets (physical/personal, e.g. home, car) ----------------


class AssetIn(BaseModel):
    id: str | None = None
    name: str
    asset_type: AssetType
    purchase_value: float = Field(ge=0)
    purchase_date: date | None = None
    current_value: float = Field(ge=0)
    current_value_updated_at: date | None = None
    notes: str | None = None


class AssetOut(ORMModel):
    id: str
    name: str
    asset_type: str
    purchase_value: float
    purchase_date: date | None
    current_value: float
    current_value_updated_at: date | None
    status: str
    sold_value: float | None
    sold_date: date | None
    notes: str | None
    created_at: datetime


class AssetSellIn(BaseModel):
    sold_value: float = Field(ge=0)
    sold_date: date | None = None


# ---------------- category groups ----------------


class CategoryGroupIn(BaseModel):
    id: str | None = None
    name: str
    color: str | None = None
    sort_order: int = 0
    is_essential: bool = False


class CategoryGroupOut(ORMModel):
    id: str
    name: str
    color: str | None
    sort_order: int
    is_essential: bool
    created_at: datetime


# ---------------- categories ----------------


class CategoryIn(BaseModel):
    id: str | None = None
    name: str
    group_id: str
    kind: EntryType
    color: str | None = None
    is_archived: bool = False


class CategoryOut(ORMModel):
    id: str
    name: str
    group_id: str | None
    kind: str
    color: str | None
    is_archived: bool
    created_at: datetime


# ---------------- category rules ----------------


class CategoryRuleIn(BaseModel):
    id: str | None = None
    keyword: str
    category_id: str


class CategoryRuleOut(ORMModel):
    id: str
    keyword: str
    category_id: str
    created_at: datetime


# ---------------- entries ----------------


class EntryIn(BaseModel):
    id: str | None = None
    type: EntryType
    amount: float = Field(ge=0)
    entry_date: date
    payee: str | None = None
    category_id: str | None = None
    account_id: str | None = None
    goal_id: str | None = None
    is_recurring: bool = False
    recurrence_interval: RecurrenceInterval = None
    notes: str | None = None
    import_batch_id: str | None = None


class EntryOut(ORMModel):
    id: str
    type: str
    amount: float
    entry_date: date
    payee: str | None
    category_id: str | None
    account_id: str | None
    goal_id: str | None
    is_recurring: bool
    recurrence_interval: str | None
    notes: str | None
    created_at: datetime


# ---------------- budgets ----------------


class BudgetIn(BaseModel):
    id: str | None = None
    category_id: str
    period: BudgetPeriod = "monthly"
    amount: float
    warning_threshold: float = 80
    critical_threshold: float = 100


class BudgetOut(ORMModel):
    id: str
    category_id: str
    period: str
    amount: float
    warning_threshold: float
    critical_threshold: float
    created_at: datetime


# ---------------- goals ----------------


class GoalIn(BaseModel):
    id: str | None = None
    name: str
    goal_type: GoalType
    target_amount: float
    current_amount: float = 0
    target_date: date | None = None


class GoalOut(ORMModel):
    id: str
    name: str
    goal_type: str
    target_amount: float
    current_amount: float
    target_date: date | None
    achieved_at: date | None
    created_at: datetime


# ---------------- forecast assumptions ----------------


class AssumptionIn(BaseModel):
    id: str | None = None
    name: str
    annual_return_rate: float = 0.07
    inflation_rate: float = 0.03
    years_horizon: int = 10
    is_active: bool = True


class AssumptionOut(ORMModel):
    id: str
    name: str
    annual_return_rate: float
    inflation_rate: float
    years_horizon: int
    is_active: bool
    created_at: datetime


# ---------------- scenarios (sandbox what-if drafts, never touch real data) ----------------

ScenarioType = Literal["custom", "best_case", "expected_case", "worst_case"]


class ScenarioAccountConfigIn(BaseModel):
    account_id: str
    growth_rate: float | None = None
    include_in_growth: bool = True


class ScenarioAccountConfigOut(ORMModel):
    account_id: str
    growth_rate: float | None
    include_in_growth: bool


class ScenarioAssetConfigIn(BaseModel):
    asset_id: str
    growth_rate: float | None = None
    include_in_growth: bool = True


class ScenarioAssetConfigOut(ORMModel):
    asset_id: str
    growth_rate: float | None
    include_in_growth: bool


class ScenarioIncomeSourceIn(BaseModel):
    name: str
    monthly_amount: float
    growth_rate: float = 0.0


class ScenarioIncomeSourceOut(ORMModel):
    id: str
    name: str
    monthly_amount: float
    growth_rate: float


class ScenarioIn(BaseModel):
    id: str | None = None
    name: str
    description: str | None = None
    scenario_type: ScenarioType = "custom"
    years_horizon: int = Field(default=10, ge=1, le=50)
    investment_return_rate: float = 0.07
    personal_asset_growth_rate: float = 0.02
    monthly_contribution_override: float | None = None
    income_growth_rate: float = 0.0
    is_adopted: bool = False
    account_configs: list[ScenarioAccountConfigIn] = Field(default_factory=list)
    asset_configs: list[ScenarioAssetConfigIn] = Field(default_factory=list)
    income_sources: list[ScenarioIncomeSourceIn] = Field(default_factory=list)


class ScenarioOut(ORMModel):
    id: str
    name: str
    description: str | None
    scenario_type: str
    years_horizon: int
    investment_return_rate: float
    personal_asset_growth_rate: float
    monthly_contribution_override: float | None
    income_growth_rate: float
    is_adopted: bool
    created_at: datetime
    account_configs: list[ScenarioAccountConfigOut] = []
    asset_configs: list[ScenarioAssetConfigOut] = []
    income_sources: list[ScenarioIncomeSourceOut] = []


class ScenarioProjectionPoint(BaseModel):
    year: int
    liquid: float
    investments: float
    personal_assets: float
    illiquid_other: float
    net_worth: float


# ---------------- watchlist ----------------


class WatchlistItemIn(BaseModel):
    id: str | None = None
    name: str
    item_type: WatchlistItemType
    symbol: str | None = None
    status: WatchlistStatus = "watching"
    target_price: float | None = None
    current_price: float | None = None
    currency: str = "USD"
    thesis: str | None = None
    url: str | None = None
    priority: int = 0


class WatchlistItemOut(ORMModel):
    id: str
    name: str
    item_type: str
    symbol: str | None
    status: str
    target_price: float | None
    current_price: float | None
    currency: str
    thesis: str | None
    url: str | None
    priority: int
    created_at: datetime


# ---------------- topics ----------------


class TopicIn(BaseModel):
    id: str | None = None
    title: str
    description: str
    category: str | None = None
    status: TopicStatus = "exploring"
    related_goal_id: str | None = None
    priority: int = 0


class TopicOut(ORMModel):
    id: str
    title: str
    description: str
    category: str | None
    status: str
    related_goal_id: str | None
    priority: int
    created_at: datetime


# ---------------- decisions (Jev decision agent) ----------------


class DecisionOptionIn(BaseModel):
    name: str
    description: str | None = None


class DecisionCreateIn(BaseModel):
    question: str
    options: list[DecisionOptionIn] = Field(min_length=2)
    notes: str | None = None


class DecisionOut(BaseModel):
    id: str
    session_id: str | None = None
    round_number: int | None = None
    question: str
    notes: str | None
    options: list[DecisionOptionIn]
    chosen_option: str | None
    confidence: float | None
    probabilities: dict[str, float]
    profile_snapshot: dict | None
    status: str
    error: str | None
    created_at: datetime


class JevStatus(BaseModel):
    enabled: bool
    model: str | None
    base_url: str | None


class DecisionContextIn(BaseModel):
    content: str


class DecisionContextOut(BaseModel):
    content: str
    updated_at: datetime


class DecisionPlanIn(BaseModel):
    content: str


class DecisionPlanOut(BaseModel):
    content: str
    updated_at: datetime


class AutoSessionStartIn(BaseModel):
    plan_brief: str


class AutoSessionOut(BaseModel):
    id: str
    plan_brief: str
    status: str
    rounds_completed: int
    created_at: datetime
    updated_at: datetime


class AutoSessionStartOut(BaseModel):
    session: AutoSessionOut
    context: str
    plan: str


class AutoStepOut(BaseModel):
    session: AutoSessionOut
    decision: DecisionOut | None
    done: bool
    message: str | None = None


# ---------------- analytics ----------------


class NetWorthSummary(BaseModel):
    total: float
    liquid: float
    illiquid: float
    investments: float
    # Held (non-sold) physical assets like property/vehicles — already included in `illiquid`.
    personal_assets: float


class CashflowPoint(BaseModel):
    month: str
    label: str
    incoming: float
    outgoing: float
    net: float


class CategoryGroupTotal(BaseModel):
    group_id: str | None
    group_name: str
    color: str | None
    total: float


class BudgetStatus(BaseModel):
    budget_id: str
    category_id: str
    category_name: str
    period: BudgetPeriod
    amount: float
    spent: float
    percent: float
    status: Literal["ok", "warning", "critical"]
    projected_period_end: float


class LiquidityInfo(BaseModel):
    liquid_balance: float
    avg_monthly_essential_spend: float
    months_of_runway: float | None


class AssetPerformance(BaseModel):
    asset_id: str
    name: str
    asset_type: str
    status: str
    purchase_value: float
    current_value: float
    gain_loss: float
    gain_loss_percent: float | None
    holding_period_days: int | None


class NetWorthProjectionPoint(BaseModel):
    year: int
    liquid: float
    investments: float
    illiquid: float
    net_worth: float


class IncomeForecastPoint(BaseModel):
    month: str
    label: str
    income: float


class IncomeForecastSummary(BaseModel):
    history: list[IncomeForecastPoint]
    forecast: list[IncomeForecastPoint]
    avg_monthly_income: float
    recurring_monthly_income: float
    trend_monthly_change: float


class AllocationSlice(BaseModel):
    label: str
    amount: float
    percent: float


class DiversificationSummary(BaseModel):
    allocations: list[AllocationSlice]
    total_allocatable: float
    largest_holding_label: str | None
    concentration_percent: float


class GoalFeasibility(BaseModel):
    goal_id: str
    name: str
    goal_type: str
    target_amount: float
    current_amount: float
    remaining_amount: float
    target_date: date | None
    months_remaining: int | None
    required_monthly_contribution: float | None
    status: Literal["on_track", "at_risk", "off_track", "no_target_date"]


class AnalyticsSummary(BaseModel):
    net_worth: NetWorthSummary
    liquidity: LiquidityInfo
    cashflow: list[CashflowPoint]
    category_breakdown: list[CategoryGroupTotal]
    budget_statuses: list[BudgetStatus]
    asset_performance: list[AssetPerformance]
    income_forecast: IncomeForecastSummary
    diversification: DiversificationSummary
    goal_feasibility: list[GoalFeasibility]


# ---------------- agents ----------------


class AgentInfo(BaseModel):
    id: str
    name: str
    version: str
    description: str
    reads: list[str]
    writes: list[str]


class AgentRunResult(BaseModel):
    agent_id: str
    status: Literal["ok", "error"]
    summary: str | None = None
    facts: dict | None = None
    error: str | None = None


class InsightOut(ORMModel):
    id: str
    agent_id: str
    severity: str
    summary: str
    facts_json: str
    created_at: datetime


class AgentExecutionOut(ORMModel):
    id: str
    agent_id: str
    agent_version: str
    status: str
    input_ref: str
    output: str | None
    error: str | None
    created_at: datetime


# ---------------- statement imports (queued upload -> review -> apply) ----------------


class ParsedStatementTransaction(BaseModel):
    entry_date: str | None
    payee: str | None
    amount: float | None
    type: EntryType
    category_id: str | None


class StatementImportOut(ORMModel):
    id: str
    account_id: str
    file_name: str
    source_type: str
    status: StatementImportStatus
    error: str | None
    statement_period: str | None
    transaction_count: int
    inserted_count: int
    updated_count: int
    statement_balance: float | None
    minimum_due: float | None
    due_date: date | None
    paid: bool
    created_at: datetime
    applied_at: datetime | None


class StatementImportDetail(StatementImportOut):
    transactions: list[ParsedStatementTransaction]


class StatementApplyTransaction(BaseModel):
    entry_date: date
    payee: str | None = None
    amount: float = Field(ge=0)
    type: EntryType
    category_id: str | None = None
    goal_id: str | None = None


class StatementApplyIn(BaseModel):
    transactions: list[StatementApplyTransaction]
    # credit_card-only informational fields — never used in net worth/analytics
    statement_balance: float | None = None
    minimum_due: float | None = None
    due_date: date | None = None


class StatementApplyResult(BaseModel):
    import_id: str
    inserted_count: int
    updated_count: int
    candidate_count: int


# ---------------- keyword auto-learning ----------------


class KeywordCandidateOut(ORMModel):
    id: str
    keyword: str
    sample_payee: str | None
    occurrence_count: int
    suggested_category_id: str | None
    status: KeywordCandidateStatus
    created_at: datetime
    updated_at: datetime


class KeywordCandidateDecisionIn(BaseModel):
    category_id: str | None = None  # override the suggestion; required if none was ever suggested


# ---------------- reminders ----------------


class ReminderIn(BaseModel):
    id: str | None = None
    account_id: str
    frequency: ReminderFrequency
    next_due_date: date | None = None  # defaults to "today + frequency" when creating
    is_active: bool = True


class ReminderOut(ORMModel):
    id: str
    account_id: str
    frequency: str
    next_due_date: date
    last_completed_at: date | None
    is_active: bool
    created_at: datetime
    is_due: bool


# ---------------- background jobs (statement parse queue) ----------------


class JobOut(ORMModel):
    id: str
    job_type: str
    status: JobStatus
    error: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


# ---------------- budget history / rollups ----------------


class BudgetHistoryOut(ORMModel):
    id: str
    budget_id: str
    category_id: str
    period: str
    amount: float
    warning_threshold: float
    critical_threshold: float
    effective_from: date
    created_at: datetime


class BudgetPeriodStatus(BaseModel):
    period_key: str  # e.g. "2026-09", "2026-Q3", "2026"
    period_label: str
    budget_id: str
    category_id: str
    category_name: str
    amount: float
    spent: float
    percent: float
    status: Literal["ok", "warning", "critical"]


class BudgetHistorySummary(BaseModel):
    granularity: BudgetHistoryGranularity
    periods: list[BudgetPeriodStatus]
