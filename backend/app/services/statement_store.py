"""Persists uploaded statement files inside the owning account's own folder
(backend/data/users/<account id>/statements/).

That directory is already covered by the repo's blanket `backend/data/` .gitignore rule, so
uploaded statements (which may contain real transaction history) are never committed.
"""
from __future__ import annotations

import re
import uuid
from pathlib import Path

from app.config import BACKEND_DIR, USERS_DIR, user_dir


def _safe_filename(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("_") or "statement"


def save_statement_file(user_id: str, account_id: str, filename: str, data: bytes) -> str:
    """Writes `data` to disk and returns a path relative to BACKEND_DIR (stored in the DB)."""
    target_dir = user_dir(user_id) / "statements" / _safe_filename(account_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid.uuid4()}_{_safe_filename(filename)}"
    target_path = target_dir / stored_name
    target_path.write_bytes(data)
    return str(target_path.relative_to(BACKEND_DIR))


def _resolve(stored_path: str) -> Path:
    """Stored paths can arrive via cloud sync, so never trust them to stay inside the data folder."""
    path = (BACKEND_DIR / stored_path).resolve()
    if USERS_DIR.resolve() not in path.parents:
        raise ValueError("Statement path is outside the account data folder")
    return path


def read_statement_file(stored_path: str) -> bytes:
    return _resolve(stored_path).read_bytes()


def delete_statement_file(stored_path: str | None) -> None:
    if not stored_path:
        return
    try:
        path = _resolve(stored_path)
    except ValueError:
        return
    if path.exists():
        path.unlink()
