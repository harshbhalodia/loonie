"""Multi-currency support: base currency, stored FX rates, live-rate sync and conversion.

Every balance keeps its own currency. For totals we convert into the user's base currency using
the stored rates (`WealthFxRate.rate_to_base` = base units per 1 unit of that currency). Rates come
from a free public rate API on demand; users can also pin a rate by hand.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.models import (
    WealthAccount,
    WealthAsset,
    WealthCurrencySettings,
    WealthFxRate,
    WealthWatchlistItem,
)
from app.services.currencies import CURRENCIES, normalize_code

log = logging.getLogger(__name__)

# Tried in order; both are free and need no API key.
PROVIDERS: tuple[tuple[str, str], ...] = (
    ("open.er-api.com", "https://open.er-api.com/v6/latest/{base}"),
    ("frankfurter.dev", "https://api.frankfurter.dev/v1/latest?base={base}"),
)
FETCH_TIMEOUT = 8.0
STALE_AFTER = timedelta(hours=24)
RETRY_AFTER = timedelta(minutes=10)
CREDIT_CARD_ACCOUNT_TYPE = "credit_card"


class FxError(RuntimeError):
    pass


@dataclass
class LiveRates:
    per_base: dict[str, float]  # units of currency per 1 base
    as_of: datetime
    provider: str


@dataclass
class SyncResult:
    updated: list[str] = field(default_factory=list)
    skipped_manual: list[str] = field(default_factory=list)
    unavailable: list[str] = field(default_factory=list)
    provider: str | None = None


@dataclass
class FxContext:
    base: str
    rates: dict[str, float]  # code -> base units per 1 unit; always includes base -> 1.0
    account_currency: dict[str, str]

    def factor(self, code: str) -> float | None:
        return self.rates.get(code)


# ---------------------------------------------------------------------------
# Settings + rates
# ---------------------------------------------------------------------------


def get_settings(db: Session, user_id: str) -> WealthCurrencySettings:
    row = db.query(WealthCurrencySettings).filter(WealthCurrencySettings.user_id == user_id).first()
    if row is None:
        row = WealthCurrencySettings(id="currency-settings", user_id=user_id, base_currency="USD")
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def get_base_currency(db: Session, user_id: str) -> str:
    return normalize_code(get_settings(db, user_id).base_currency)


def list_rate_rows(db: Session, user_id: str) -> list[WealthFxRate]:
    return db.query(WealthFxRate).filter(WealthFxRate.user_id == user_id).order_by(WealthFxRate.currency).all()


def used_currencies(db: Session, user_id: str) -> set[str]:
    codes = {normalize_code(c) for (c,) in db.query(WealthAccount.currency).filter(WealthAccount.user_id == user_id)}
    codes |= {normalize_code(c) for (c,) in db.query(WealthAsset.currency).filter(WealthAsset.user_id == user_id)}
    return codes


def build_context(db: Session, user_id: str) -> FxContext:
    base = get_base_currency(db, user_id)
    rates = {r.currency: r.rate_to_base for r in list_rate_rows(db, user_id) if r.rate_to_base > 0}
    rates[base] = 1.0
    account_currency = {
        acc_id: normalize_code(cur)
        for acc_id, cur in db.query(WealthAccount.id, WealthAccount.currency).filter(WealthAccount.user_id == user_id)
    }
    return FxContext(base=base, rates=rates, account_currency=account_currency)


def missing_rates(db: Session, user_id: str, ctx: FxContext | None = None) -> list[str]:
    ctx = ctx or build_context(db, user_id)
    return sorted(code for code in used_currencies(db, user_id) if code not in ctx.rates)


# ---------------------------------------------------------------------------
# Live provider
# ---------------------------------------------------------------------------


def _parse_er_api(payload: dict) -> tuple[dict[str, float], datetime]:
    if payload.get("result") != "success" or not isinstance(payload.get("rates"), dict):
        raise FxError(f"unexpected response ({payload.get('error-type', 'no rates')})")
    ts = payload.get("time_last_update_unix")
    as_of = datetime.utcfromtimestamp(ts) if isinstance(ts, (int, float)) else datetime.utcnow()
    return payload["rates"], as_of


def _parse_frankfurter(payload: dict) -> tuple[dict[str, float], datetime]:
    if not isinstance(payload.get("rates"), dict):
        raise FxError("unexpected response")
    try:
        as_of = datetime.strptime(str(payload.get("date")), "%Y-%m-%d")
    except ValueError:
        as_of = datetime.utcnow()
    return payload["rates"], as_of


_PARSERS = {"open.er-api.com": _parse_er_api, "frankfurter.dev": _parse_frankfurter}


def fetch_live_rates(base: str) -> LiveRates:
    """Latest rates against `base` from the first provider that answers."""
    errors: list[str] = []
    for name, url in PROVIDERS:
        try:
            response = httpx.get(url.format(base=base), timeout=FETCH_TIMEOUT, follow_redirects=True)
            response.raise_for_status()
            raw, as_of = _PARSERS[name](response.json())
        except (httpx.HTTPError, ValueError, FxError) as exc:
            errors.append(f"{name}: {exc}")
            continue
        per_base = {
            str(code).upper(): float(value)
            for code, value in raw.items()
            if isinstance(value, (int, float)) and value > 0
        }
        per_base[base] = 1.0
        return LiveRates(per_base=per_base, as_of=as_of, provider=name)
    raise FxError("Could not fetch live exchange rates (" + "; ".join(errors) + ")")


# ---------------------------------------------------------------------------
# Sync / manual edits
# ---------------------------------------------------------------------------


def _upsert_rate(db: Session, user_id: str, code: str, rate: float, source: str, as_of: datetime | None) -> WealthFxRate:
    row = (
        db.query(WealthFxRate).filter(WealthFxRate.user_id == user_id, WealthFxRate.currency == code).first()
    )
    if row is None:
        row = WealthFxRate(id=f"fx-{code}", user_id=user_id, currency=code, rate_to_base=rate)
        db.add(row)
    row.rate_to_base = rate
    row.source = source
    row.as_of = as_of
    row.updated_at = datetime.utcnow()
    return row


def sync_rates(
    db: Session, user_id: str, extra_codes: set[str] | None = None, override_manual: bool = False
) -> SyncResult:
    """Refreshes live rates for every currency in use, plus already-tracked ones and `extra_codes`.

    Manually pinned rates are left alone unless `override_manual` is set (used when the user
    explicitly reverts one to live). Raises FxError when no provider answers; stored rates stay.
    """
    settings = get_settings(db, user_id)
    base = normalize_code(settings.base_currency)
    existing = {r.currency: r for r in list_rate_rows(db, user_id)}
    targets = (used_currencies(db, user_id) | set(existing) | (extra_codes or set())) - {base}

    now = datetime.utcnow()
    settings.last_attempt_at = now
    result = SyncResult()
    if not targets:
        settings.last_synced_at = now
        settings.last_error = None
        db.commit()
        return result

    try:
        live = fetch_live_rates(base)
    except FxError as exc:
        settings.last_error = str(exc)
        db.commit()
        raise

    result.provider = live.provider
    for code in sorted(targets):
        row = existing.get(code)
        if row is not None and row.source == "manual" and not override_manual:
            result.skipped_manual.append(code)
            continue
        per_base = live.per_base.get(code)
        if not per_base:
            result.unavailable.append(code)
            continue
        _upsert_rate(db, user_id, code, 1.0 / per_base, "live", live.as_of)
        result.updated.append(code)

    settings.last_synced_at = now
    settings.last_error = (
        "No live rate available for: " + ", ".join(result.unavailable) + ". Enter one manually." if result.unavailable else None
    )
    db.commit()
    return result


def ensure_rates(db: Session, user_id: str) -> None:
    """Best-effort auto-fetch when a currency in use has no rate yet (throttled, never raises)."""
    if not missing_rates(db, user_id):
        return
    settings = get_settings(db, user_id)
    if settings.last_attempt_at and datetime.utcnow() - settings.last_attempt_at < RETRY_AFTER:
        return
    try:
        sync_rates(db, user_id)
    except FxError as exc:
        log.info("automatic FX sync failed: %s", exc)


def set_manual_rate(db: Session, user_id: str, code: str, rate_to_base: float) -> WealthFxRate:
    row = _upsert_rate(db, user_id, code, rate_to_base, "manual", datetime.utcnow())
    db.commit()
    db.refresh(row)
    return row


def track_or_revert_live(db: Session, user_id: str, code: str) -> WealthFxRate:
    """Fetches one currency's live rate (adds it if untracked, replaces a manual pin)."""
    result = sync_rates(db, user_id, extra_codes={code}, override_manual=True)
    if code in result.unavailable:
        raise FxError(f"No live rate is available for {code}. Enter one manually.")
    row = db.query(WealthFxRate).filter(WealthFxRate.user_id == user_id, WealthFxRate.currency == code).first()
    if row is None:
        raise FxError(f"{code} is the base currency and needs no rate.")
    return row


def remove_rate(db: Session, user_id: str, code: str) -> None:
    row = db.query(WealthFxRate).filter(WealthFxRate.user_id == user_id, WealthFxRate.currency == code).first()
    if row is not None:
        db.delete(row)
        db.commit()


def set_base_currency(db: Session, user_id: str, new_base: str, relabel_existing: bool) -> WealthCurrencySettings:
    """Switches the reporting currency, re-expressing stored rates so nothing has to be refetched.

    `relabel_existing` moves accounts/assets/watchlist items currently labelled with the old base
    to the new one (for people who never set a currency and just want everything in theirs).
    """
    settings = get_settings(db, user_id)
    old_base = normalize_code(settings.base_currency)
    if new_base == old_base:
        return settings

    rows = {r.currency: r for r in list_rate_rows(db, user_id)}
    pivot = rows[new_base].rate_to_base if new_base in rows and rows[new_base].rate_to_base > 0 else None

    if pivot:
        for code, row in rows.items():
            if code == new_base:
                db.delete(row)
            else:
                row.rate_to_base = row.rate_to_base / pivot
                row.updated_at = datetime.utcnow()
        _upsert_rate(db, user_id, old_base, 1.0 / pivot, "live", None)
    else:
        for row in rows.values():
            db.delete(row)

    if relabel_existing:
        for model in (WealthAccount, WealthAsset, WealthWatchlistItem):
            for obj in db.query(model).filter(model.user_id == user_id).all():
                if normalize_code(obj.currency) == old_base:
                    obj.currency = new_base

    settings.base_currency = new_base
    settings.last_error = None
    settings.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(settings)
    return settings


# ---------------------------------------------------------------------------
# Conversion for analytics
# ---------------------------------------------------------------------------


def _clone(obj: Any, **overrides: Any) -> SimpleNamespace:
    """Detached copy of an ORM row so converted amounts can never be flushed back to the database."""
    data = {c.name: getattr(obj, c.name) for c in obj.__table__.columns}
    data.update(overrides)
    return SimpleNamespace(**data)


def to_base(
    db: Session,
    user_id: str,
    accounts: list | None = None,
    assets: list | None = None,
    entries: list | None = None,
) -> tuple[list, list, list]:
    """Returns (accounts, assets, entries) with every amount expressed in the base currency.

    Single-currency users get their original objects back untouched. Amounts in a currency
    without a known rate become 0 (and show up in `missing_rates`) rather than being guessed.
    """
    accounts = list(accounts or [])
    assets = list(assets or [])
    entries = list(entries or [])

    ctx = build_context(db, user_id)
    base = ctx.base

    def needs_conversion() -> bool:
        if any(normalize_code(a.currency, base) != base for a in accounts):
            return True
        if any(normalize_code(a.currency, base) != base for a in assets):
            return True
        return any(ctx.account_currency.get(e.account_id, base) != base for e in entries if e.account_id)

    if not needs_conversion():
        return accounts, assets, entries

    ensure_rates(db, user_id)
    ctx = build_context(db, user_id)

    def factor(code: str) -> float:
        return ctx.factor(code) or 0.0

    out_accounts = []
    for acc in accounts:
        f = factor(normalize_code(acc.currency, base))
        out_accounts.append(
            _clone(
                acc,
                currency=base,
                opening_balance=acc.opening_balance * f,
                current_balance=acc.current_balance * f,
            )
        )

    out_assets = []
    for asset in assets:
        f = factor(normalize_code(asset.currency, base))
        out_assets.append(
            _clone(
                asset,
                currency=base,
                purchase_value=asset.purchase_value * f,
                current_value=asset.current_value * f,
                sold_value=None if asset.sold_value is None else asset.sold_value * f,
            )
        )

    out_entries = []
    for entry in entries:
        code = ctx.account_currency.get(entry.account_id, base) if entry.account_id else base
        out_entries.append(entry if code == base else _clone(entry, amount=entry.amount * factor(code)))

    return out_accounts, out_assets, out_entries


# ---------------------------------------------------------------------------
# Reporting: per-currency breakdown + status
# ---------------------------------------------------------------------------


def net_worth_by_currency(db: Session, user_id: str, accounts: list, assets: list) -> list[dict]:
    """Net worth per currency in its own units, plus its value in the base currency."""
    ctx = build_context(db, user_id)
    sources = {r.currency: r.source for r in list_rate_rows(db, user_id)}
    buckets: dict[str, dict] = {}

    def bucket(code: str) -> dict:
        return buckets.setdefault(code, {"native_total": 0.0, "account_count": 0, "asset_count": 0})

    for acc in accounts:
        if acc.type == CREDIT_CARD_ACCOUNT_TYPE:
            continue
        code = normalize_code(acc.currency, ctx.base)
        b = bucket(code)
        b["native_total"] += -abs(acc.current_balance) if acc.type in ("credit", "loan") else acc.current_balance
        b["account_count"] += 1

    for asset in assets:
        if asset.status != "holding":
            continue
        code = normalize_code(asset.currency, ctx.base)
        b = bucket(code)
        b["native_total"] += asset.current_value
        b["asset_count"] += 1

    items = []
    for code, b in buckets.items():
        rate = ctx.factor(code)
        base_total = round(b["native_total"] * rate, 2) if rate is not None else None
        items.append(
            {
                "currency": code,
                "name": CURRENCIES.get(code, code),
                "native_total": round(b["native_total"], 2),
                "rate_to_base": rate,
                "base_total": base_total,
                "rate_source": "base" if code == ctx.base else sources.get(code),
                "account_count": b["account_count"],
                "asset_count": b["asset_count"],
            }
        )

    gross = sum(abs(i["base_total"]) for i in items if i["base_total"] is not None)
    for item in items:
        item["percent"] = round(abs(item["base_total"]) / gross * 100, 2) if gross and item["base_total"] is not None else 0.0
    items.sort(key=lambda i: (i["base_total"] is None, -abs(i["base_total"] or 0)))
    return items


def status(db: Session, user_id: str) -> dict:
    settings = get_settings(db, user_id)
    ctx = build_context(db, user_id)
    used_foreign = {c for c in used_currencies(db, user_id) if c != ctx.base}
    missing = sorted(c for c in used_foreign if c not in ctx.rates)
    synced = settings.last_synced_at
    stale = bool(used_foreign) and (synced is None or datetime.utcnow() - synced > STALE_AFTER)
    return {
        "base_currency": ctx.base,
        "last_synced_at": synced,
        "missing_rates": missing,
        "stale": stale,
        "last_error": settings.last_error,
    }
