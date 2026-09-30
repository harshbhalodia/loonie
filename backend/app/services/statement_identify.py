"""Works out what an uploaded statement is (type, currency, which of the user's accounts) without AI.

Pilot uses this so people can just drop a file into the chat: cheap text heuristics on the PDF plus
the user's own account names/institutions pick the account, and the user is only asked when the
match is genuinely ambiguous.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.models import WealthAccount
from app.services.currencies import CURRENCIES
from app.services.statement_parsing import extract_pdf_text

KIND_KEYWORDS: dict[str, tuple[str, ...]] = {
    "credit_card": (
        "minimum payment", "payment due date", "credit limit", "new balance", "credit card",
        "visa", "mastercard", "american express", "amex", "statement balance",
    ),
    "bank": (
        "chequing", "checking", "savings", "opening balance", "closing balance",
        "deposits", "withdrawals", "account statement", "e-transfer", "direct deposit",
    ),
    "investment": ("portfolio", "holdings", "market value", "securities", "dividends", "brokerage"),
    "loan": ("mortgage", "principal", "loan", "interest rate", "amortization"),
}
KIND_LABELS = {
    "credit_card": "credit card",
    "bank": "bank account",
    "investment": "investment",
    "loan": "loan",
    "unknown": "statement",
}
KIND_ACCOUNT_TYPES = {
    "credit_card": {"credit_card", "credit"},
    "bank": {"checking", "savings"},
    "investment": {"investment", "retirement"},
    "loan": {"loan"},
}
SYMBOL_CURRENCY = {"£": "GBP", "€": "EUR", "₹": "INR", "¥": "JPY"}
LAST4_RE = re.compile(r"(?:ending in|ending|account number|acct|card number|card no\.?)[^0-9\n]{0,12}(?:[x*•\-\s]{0,16})(\d{4})\b", re.I)
MASKED_RE = re.compile(r"(?:[x*•]{3,}[\s\-]*)(\d{4})\b", re.I)


@dataclass
class StatementGuess:
    file_type: str
    kind: str = "unknown"
    currency: str | None = None
    last4: list[str] = field(default_factory=list)
    matched_account_id: str | None = None
    confidence: str = "low"
    candidates: list[dict] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)

    @property
    def kind_label(self) -> str:
        return KIND_LABELS.get(self.kind, "statement")


def _file_type(filename: str, data: bytes) -> str:
    lower = filename.lower()
    if data[:5] == b"%PDF-" or lower.endswith(".pdf"):
        return "pdf"
    if lower.endswith(".csv") or lower.endswith(".txt"):
        return "csv"
    return "other"


def _detect_kind(text: str) -> str:
    scores = {kind: sum(text.count(word) for word in words) for kind, words in KIND_KEYWORDS.items()}
    kind, best = max(scores.items(), key=lambda item: item[1])
    return kind if best >= 2 else "unknown"


def _detect_currency(raw_text: str, upper_text: str) -> str | None:
    counts = {}
    for code in CURRENCIES:
        found = len(re.findall(rf"\b{code}\b", upper_text))
        if found >= 2:
            counts[code] = found
    if counts:
        return max(counts.items(), key=lambda item: item[1])[0]
    for symbol, code in SYMBOL_CURRENCY.items():
        if raw_text.count(symbol) >= 2:
            return code
    return None


def _account_score(acc: WealthAccount, text: str, filename: str, guess: StatementGuess) -> tuple[int, list[str]]:
    score, why = 0, []
    name, institution = acc.name.lower().strip(), (acc.institution or "").lower().strip()
    if institution and len(institution) > 2 and institution in text:
        score += 5
        why.append(f"mentions {acc.institution}")
    if name and len(name) > 2 and name in text:
        score += 4
        why.append(f"mentions {acc.name}")
    digits = re.findall(r"\d{4}", f"{acc.name} {acc.institution or ''}")
    if any(d in guess.last4 for d in digits):
        score += 6
        why.append("card/account number matches")
    if (institution and institution in filename) or (name and len(name) > 2 and name in filename):
        score += 3
        why.append("file name matches")
    if acc.type in KIND_ACCOUNT_TYPES.get(guess.kind, set()):
        score += 2
        why.append(f"is a {KIND_LABELS[guess.kind]} account")
    if guess.currency and (acc.currency or "").upper() == guess.currency:
        score += 1
    return score, why


def identify_statement(filename: str, data: bytes, accounts: list[WealthAccount]) -> StatementGuess:
    guess = StatementGuess(file_type=_file_type(filename, data))
    lower_name = filename.lower()

    if guess.file_type != "pdf":
        guess.reasons.append("Not a PDF — CSV files need a column mapping.")
        return guess

    try:
        raw_text = extract_pdf_text(data)
    except Exception:  # scanned/unreadable PDFs still get a name-based guess below
        raw_text = ""
        guess.reasons.append("No readable text in the PDF, so I matched on the file name only.")

    text = raw_text.lower()
    guess.kind = _detect_kind(text)
    guess.currency = _detect_currency(raw_text, raw_text.upper())
    guess.last4 = list(dict.fromkeys(LAST4_RE.findall(raw_text) + MASKED_RE.findall(raw_text)))[:4]

    scored = []
    for acc in accounts:
        score, why = _account_score(acc, text, lower_name, guess)
        scored.append((score, acc, why))
    scored.sort(key=lambda item: item[0], reverse=True)

    guess.candidates = [{"id": a.id, "name": a.name, "score": s} for s, a, _ in scored[:5] if s > 0]
    if scored and scored[0][0] >= 4 and (len(scored) == 1 or scored[0][0] - scored[1][0] >= 2):
        guess.matched_account_id = scored[0][1].id
        guess.confidence = "high" if scored[0][0] >= 7 else "medium"
        guess.reasons.extend(scored[0][2])
    elif len(accounts) == 1:
        guess.matched_account_id = accounts[0].id
        guess.confidence = "medium"
        guess.reasons.append("it is your only account")
    return guess
