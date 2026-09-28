"""Publisher feedback export: an explicit, user-triggered action only — never automatic.

Loonie's marketplace pitch to publishers (see the localagents repo's
docs/architecture/blueprint-marketplace.md) is that a blueprint's publisher never receives a
user's data. Run history/facts stay local by default. If a user wants to help a publisher
improve a blueprint, they can explicitly export ONE run as a precision-reduced bundle: exact
dollar figures are rounded to 2 significant figures (loses cents/exact-identifying precision,
keeps rough scale useful for a publisher), and nothing that identifies the user (email, user id,
account/entry ids) is ever included.
"""
from __future__ import annotations

import math
from typing import Any


def _round_significant(value: float, digits: int = 2) -> float:
    if value == 0 or not math.isfinite(value):
        return 0.0
    magnitude = math.floor(math.log10(abs(value)))
    factor = 10 ** (magnitude - digits + 1)
    return round(value / factor) * factor


def redact(value: Any) -> Any:
    """Recursively precision-reduces every numeric leaf in a facts dict/list, leaving string
    labels (statuses, categories, scenario ids) untouched — those carry no exact user data."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return _round_significant(float(value))
    if isinstance(value, dict):
        return {key: redact(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def build_export_bundle(
    *,
    blueprint_id: str,
    blueprint_version: str,
    tier: str,
    facts: dict,
    result: str,
    user_rating: str | None,
    user_note: str | None,
) -> dict:
    """The exact payload a user can download and choose to send to a blueprint's publisher.
    Contains no user identity, account ids, or exact figures — only the blueprint's own
    id/version, precision-reduced facts, the narrative it produced, and the user's own optional
    rating/note about whether it was helpful."""
    return {
        "blueprint_id": blueprint_id,
        "blueprint_version": blueprint_version,
        "tier": tier,
        "facts": redact(facts),
        "result": result,
        "user_rating": user_rating,
        "user_note": user_note,
    }
