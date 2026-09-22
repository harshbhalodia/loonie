"""Keyword auto-learning: flags recurring uncategorized statement payees as candidate keyword ->
category rules, then (optionally) asks the AI to propose a category for each — but nothing here
ever becomes a real `WealthCategoryRule` without the user explicitly approving it.
"""
from __future__ import annotations

import json
import re

from sqlalchemy.orm import Session

from app.models import User, WealthCategory, WealthCategoryRule, WealthKeywordCandidate
from app.services import ai_provider

SYSTEM_PROMPT = """You suggest a category for recurring, still-uncategorized transaction keywords.
Return ONLY a JSON array (no markdown fences, no commentary) — one object per input keyword, with:
- "keyword": copied exactly from the input
- "category": your best-guess category name chosen from "known_categories", or null if unsure.
Never invent a category name that isn't in "known_categories"."""


def normalize_keyword(payee: str) -> str:
    """Best-effort merchant keyword from a raw statement payee string (drops store/reference
    numbers and extra punctuation, keeps the first couple of meaningful words)."""
    text = re.sub(r"[^A-Za-z0-9& ]", " ", payee).strip()
    text = re.sub(r"\s+", " ", text)
    tokens = [t for t in text.split(" ") if t and not t.isdigit()]
    return " ".join(tokens[:2]).strip() or text


def record_uncategorized_candidate(db: Session, user_id: str, payee: str | None) -> None:
    """Called for every applied statement transaction that landed with no category."""
    if not payee:
        return
    keyword = normalize_keyword(payee)
    if not keyword:
        return

    # already covered by a real rule — no need to flag it again
    existing_rules = db.query(WealthCategoryRule).filter(WealthCategoryRule.user_id == user_id).all()
    lowered = keyword.lower()
    if any(r.keyword.lower() in lowered or lowered in r.keyword.lower() for r in existing_rules):
        return

    candidate = (
        db.query(WealthKeywordCandidate)
        .filter(WealthKeywordCandidate.user_id == user_id)
        .filter(WealthKeywordCandidate.keyword.ilike(keyword))
        .first()
    )
    if candidate:
        if candidate.status == "pending":
            candidate.occurrence_count += 1
            candidate.sample_payee = payee
            db.add(candidate)
    else:
        db.add(
            WealthKeywordCandidate(
                user_id=user_id, keyword=keyword, sample_payee=payee, occurrence_count=1, status="pending"
            )
        )
    db.commit()


def suggest_categories(db: Session, user: User) -> list[WealthKeywordCandidate]:
    """Asks the AI to propose a category for every pending candidate with no suggestion yet.

    Raises ai_provider.AIProviderError if AI is disabled/unreachable — callers must handle it.
    """
    candidates = (
        db.query(WealthKeywordCandidate)
        .filter(
            WealthKeywordCandidate.user_id == user.id,
            WealthKeywordCandidate.status == "pending",
            WealthKeywordCandidate.suggested_category_id.is_(None),
        )
        .all()
    )
    if not candidates:
        return []

    categories = db.query(WealthCategory).filter(WealthCategory.user_id == user.id, WealthCategory.is_archived.is_(False)).all()
    category_id_by_name = {c.name.lower(): c.id for c in categories}

    prompt_context = {
        "known_categories": sorted(category_id_by_name.keys()),
        "keywords": [{"keyword": c.keyword, "sample_payee": c.sample_payee, "occurrences": c.occurrence_count} for c in candidates],
    }

    raw = ai_provider.generate(SYSTEM_PROMPT, json.dumps(prompt_context))
    cleaned = re.sub(r"^```(json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
    start, end = cleaned.find("["), cleaned.rfind("]")
    if start == -1 or end == -1 or end < start:
        raise ai_provider.AIProviderError(f"AI response was not a JSON array: {raw[:300]!r}")
    try:
        suggestions = json.loads(cleaned[start : end + 1])
    except ValueError as exc:
        raise ai_provider.AIProviderError(f"AI response was not valid JSON: {exc}") from exc

    suggestion_by_keyword = {
        str(item.get("keyword", "")).lower(): item.get("category") for item in suggestions if isinstance(item, dict)
    }

    updated: list[WealthKeywordCandidate] = []
    for candidate in candidates:
        category_name = suggestion_by_keyword.get(candidate.keyword.lower())
        category_id = category_id_by_name.get(str(category_name or "").strip().lower())
        if category_id:
            candidate.suggested_category_id = category_id
            db.add(candidate)
            updated.append(candidate)

    db.commit()
    return updated


def approve_candidate(db: Session, candidate: WealthKeywordCandidate, category_id: str) -> WealthCategoryRule:
    rule = WealthCategoryRule(user_id=candidate.user_id, keyword=candidate.keyword, category_id=category_id)
    db.add(rule)
    candidate.status = "approved"
    candidate.suggested_category_id = category_id
    db.add(candidate)
    db.commit()
    db.refresh(rule)
    return rule


def reject_candidate(db: Session, candidate: WealthKeywordCandidate) -> None:
    candidate.status = "rejected"
    db.add(candidate)
    db.commit()
