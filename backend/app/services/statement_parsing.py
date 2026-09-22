"""Shared PDF statement -> transaction-list parsing (used by both the direct parse-pdf endpoint
and the queued multi-upload flow), and the JSON-array response parsing helpers.
"""
from __future__ import annotations

import io
import json
import re
from collections import Counter

from fastapi import HTTPException
from pypdf import PdfReader
from sqlalchemy.orm import Session

from app.models import WealthCategory, WealthCategoryRule
from app.services import ai_provider

MAX_STATEMENT_CHARS = 20000

SYSTEM_PROMPT = """You extract line-item transactions from raw credit card / bank statement text.
Return ONLY a JSON array (no markdown fences, no commentary) — one object per transaction, with:
- "date": ISO format YYYY-MM-DD (infer the year from the statement header if a line only has month/day)
- "description": the merchant/payee text as printed
- "amount": a positive number
- "direction": "charge" (money spent) or "payment" (a payment, credit, or refund reducing the balance)
- "category": your best-guess category name chosen from "known_categories", or null if unsure.
  Prefer "known_keyword_mappings" whenever a transaction's description contains one of those keywords.
Skip headers, page footers, subtotals, and running-balance lines — only real transactions."""


def extract_pdf_text(data: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(data))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not read PDF: {exc}") from exc
    text = "\n".join((page.extract_text() or "") for page in reader.pages).strip()
    if not text:
        raise HTTPException(status_code=422, detail="No extractable text found in this PDF (it may be a scanned image).")
    return text


def parse_json_array(text: str) -> list[dict]:
    cleaned = re.sub(r"^```(json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    start, end = cleaned.find("["), cleaned.rfind("]")
    if start == -1 or end == -1 or end < start:
        raise ai_provider.AIProviderError(f"AI response was not a JSON array: {text[:300]!r}")
    try:
        parsed = json.loads(cleaned[start : end + 1])
    except ValueError as exc:
        raise ai_provider.AIProviderError(f"AI response was not valid JSON: {exc}") from exc
    if not isinstance(parsed, list):
        raise ai_provider.AIProviderError("AI response JSON was not a list")
    return parsed


def match_rule(description: str, rules: list[WealthCategoryRule]) -> str | None:
    lower = description.lower()
    for rule in rules:
        if rule.keyword.lower() in lower:
            return rule.category_id
    return None


def parse_pdf_to_transactions(db: Session, user_id: str, pdf_bytes: bytes, timeout: float = 600) -> list[dict]:
    """Extracts + AI-parses a PDF statement into transaction dicts (each with entry_date/payee/
    amount/type/category_id), applying the user's deterministic keyword rules as an override."""
    text = extract_pdf_text(pdf_bytes)[:MAX_STATEMENT_CHARS]

    categories = db.query(WealthCategory).filter(WealthCategory.user_id == user_id, WealthCategory.is_archived.is_(False)).all()
    rules = db.query(WealthCategoryRule).filter(WealthCategoryRule.user_id == user_id).all()
    category_id_by_name = {c.name.lower(): c.id for c in categories}
    category_name_by_id = {c.id: c.name for c in categories}

    prompt_context = {
        "known_categories": sorted(category_id_by_name.keys()),
        "known_keyword_mappings": [
            {"keyword": r.keyword, "category": category_name_by_id.get(r.category_id)} for r in rules
        ],
        "statement_text": text,
    }

    raw = ai_provider.generate(SYSTEM_PROMPT, json.dumps(prompt_context), timeout=timeout)
    items = parse_json_array(raw)

    transactions = []
    for item in items:
        if not isinstance(item, dict):
            continue
        description = str(item.get("description") or "").strip()
        try:
            amount = abs(float(item.get("amount")))
        except (TypeError, ValueError):
            continue
        entry_date = str(item.get("date") or "").strip() or None
        direction = str(item.get("direction") or "charge").lower()
        entry_type = "income" if direction in ("payment", "credit", "refund") else "expense"

        # deterministic user-defined rules always win over the model's own guess
        category_id = match_rule(description, rules)
        if not category_id:
            category_id = category_id_by_name.get(str(item.get("category") or "").strip().lower())

        transactions.append(
            {
                "entry_date": entry_date,
                "payee": description or None,
                "amount": amount,
                "type": entry_type,
                "category_id": category_id,
            }
        )

    return transactions


def derive_statement_period(transactions: list[dict]) -> str | None:
    months = [t["entry_date"][:7] for t in transactions if t.get("entry_date")]
    if not months:
        return None
    return Counter(months).most_common(1)[0][0]
