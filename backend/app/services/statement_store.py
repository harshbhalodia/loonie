"""Persists uploaded statement files to local disk under backend/data/statements/.

That directory is already covered by the repo's blanket `backend/data/` .gitignore rule, so
uploaded statements (which may contain real transaction history) are never committed.
"""
from __future__ import annotations

import re
import uuid
from pathlib import Path

from app.config import BACKEND_DIR

STATEMENTS_DIR = BACKEND_DIR / "data" / "statements"


def _safe_filename(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("_") or "statement"


def save_statement_file(user_id: str, account_id: str, filename: str, data: bytes) -> str:
    """Writes `data` to disk and returns a path relative to BACKEND_DIR (stored in the DB)."""
    target_dir = STATEMENTS_DIR / user_id / account_id
    target_dir.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid.uuid4()}_{_safe_filename(filename)}"
    target_path = target_dir / stored_name
    target_path.write_bytes(data)
    return str(target_path.relative_to(BACKEND_DIR))


def read_statement_file(stored_path: str) -> bytes:
    return (BACKEND_DIR / stored_path).read_bytes()


def delete_statement_file(stored_path: str | None) -> None:
    if not stored_path:
        return
    path = BACKEND_DIR / stored_path
    if path.exists():
        path.unlink()
