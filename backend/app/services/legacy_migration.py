"""One-time upgrade from the old single shared database (`data/lifeos.db`) to per-account folders.

Existing accounts keep their id (so already-issued sign-in tokens stay valid), password and all
data. The old database file is kept, renamed, as a safety copy — nothing is deleted.
"""
from __future__ import annotations

import logging
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

from app.config import DATA_DIR, get_database_path, user_db_path, user_dir
from app.registry import Account, RegistrySession, account_count

log = logging.getLogger("loonie.migration")

_LEGACY_BACKUP_SUFFIX = ".pre-multiuser-backup"


def _tables(con: sqlite3.Connection) -> list[str]:
    return [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]


def _columns(con: sqlite3.Connection, table: str) -> list[str]:
    return [r[1] for r in con.execute(f'PRAGMA table_info("{table}")')]


def _prune_to_user(db_path: Path, user_id: str) -> None:
    """Removes every other account's rows from a copy of the shared database."""
    con = sqlite3.connect(str(db_path))
    try:
        no_user_col: list[str] = []
        for table in _tables(con):
            if table == "alembic_version":
                continue
            cols = _columns(con, table)
            if table == "users":
                con.execute("DELETE FROM users WHERE id != ?", (user_id,))
            elif "user_id" in cols:
                con.execute(f'DELETE FROM "{table}" WHERE user_id != ?', (user_id,))
            else:
                no_user_col.append(table)
        # Child tables without their own user_id (e.g. scenario configs): drop rows whose parent went.
        for _ in range(2):
            for table in no_user_col:
                for _id, _seq, parent, from_col, to_col, *_ in con.execute(f'PRAGMA foreign_key_list("{table}")').fetchall():
                    if to_col:
                        con.execute(
                            f'DELETE FROM "{table}" WHERE "{from_col}" IS NOT NULL '
                            f'AND "{from_col}" NOT IN (SELECT "{to_col}" FROM "{parent}")'
                        )
        con.commit()
    finally:
        con.close()


def _rewrite_statement_paths(db_path: Path, user_id: str) -> None:
    """Statement files move from data/statements/<uid>/... to data/users/<uid>/statements/..."""
    con = sqlite3.connect(str(db_path))
    try:
        if "wealth_statement_imports" not in _tables(con):
            return
        rows = con.execute("SELECT id, stored_path FROM wealth_statement_imports WHERE stored_path IS NOT NULL").fetchall()
        for row_id, stored in rows:
            parts = Path(stored.replace("\\", "/")).parts
            if len(parts) >= 3 and parts[0] == "data" and parts[1] == "statements" and parts[2] == user_id:
                new_path = Path("data", "users", user_id, "statements", *parts[3:])
                con.execute("UPDATE wealth_statement_imports SET stored_path = ? WHERE id = ?", (str(new_path), row_id))
        con.commit()
    finally:
        con.close()


def migrate_legacy_database_if_needed() -> None:
    legacy_db = get_database_path()
    if not legacy_db.exists():
        return
    with RegistrySession() as registry:
        if account_count(registry) > 0:
            return

        src = sqlite3.connect(str(legacy_db))
        try:
            if "users" not in _tables(src):
                return
            legacy_users = src.execute("SELECT id, email, password_hash, created_at FROM users ORDER BY created_at").fetchall()
        finally:
            src.close()
        if not legacy_users:
            return

        log.info("upgrading shared database to per-account folders (%d account(s))", len(legacy_users))
        for index, (uid, email, password_hash, created_at) in enumerate(legacy_users):
            target = user_dir(uid)
            target.mkdir(parents=True, exist_ok=True)
            dest_db = user_db_path(uid)

            source = sqlite3.connect(str(legacy_db))
            dest = sqlite3.connect(str(dest_db))
            try:
                with dest:
                    source.backup(dest)
            finally:
                source.close()
                dest.close()

            if len(legacy_users) > 1:
                _prune_to_user(dest_db, uid)

            old_statements = DATA_DIR / "statements" / uid
            if old_statements.exists():
                shutil.copytree(old_statements, target / "statements", dirs_exist_ok=True)
            _rewrite_statement_paths(dest_db, uid)

            token_file = DATA_DIR / "google_drive_token.json"
            if index == 0 and token_file.exists():
                shutil.copyfile(token_file, target / "google_drive_token.json")

            created = datetime.fromisoformat(created_at) if isinstance(created_at, str) else datetime.utcnow()
            registry.add(Account(id=uid, email=email, password_hash=password_hash, created_at=created))
            registry.commit()

        # Keep the originals as a safety copy (renamed so it is never picked up again).
        legacy_db.rename(legacy_db.with_name(legacy_db.name + _LEGACY_BACKUP_SUFFIX))
        log.info("shared database upgraded; original kept as %s", legacy_db.name + _LEGACY_BACKUP_SUFFIX)
