"""Restore one account's database + statement files from a Google Drive backup.

Only that account's own folder (`backend/data/users/<id>/`) is ever touched. The restore is
applied immediately by swapping the files under the account's database engine; if Windows still
holds the file open, it is staged and finishes on the next start instead (`restart_required`).
"""
from __future__ import annotations

import logging
import shutil
import sqlite3
import time
import zipfile
import io
from pathlib import Path

import httpx

from app.config import DATA_DIR, USERS_DIR, get_database_path, user_db_path, user_dir
from app.services import legacy_migration
from app.services.google_drive import DRIVE_FILES_ENDPOINT, GoogleDriveError, _get_access_token

log = logging.getLogger("loonie.drive")

STAGING_NAME = "_pending_restore"
MARKER_NAME = ".pending_restore.json"
_LEGACY_STAGING = DATA_DIR / "_pending_restore"
_LEGACY_MARKER = DATA_DIR / ".pending_restore.json"


def _download_and_extract(user_id: str, file_id: str) -> Path:
    access_token = _get_access_token(user_id)
    resp = httpx.get(
        f"{DRIVE_FILES_ENDPOINT}/{file_id}",
        headers={"Authorization": f"Bearer {access_token}"},
        params={"alt": "media"},
        timeout=120,
    )
    resp.raise_for_status()

    staging = user_dir(user_id) / STAGING_NAME
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    try:
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            root = staging.resolve()
            for member in zf.infolist():
                target = (staging / member.filename).resolve()
                if target != root and root not in target.parents:
                    raise GoogleDriveError("Backup archive contains an unsafe path.")
            zf.extractall(staging)
    except zipfile.BadZipFile as exc:
        shutil.rmtree(staging, ignore_errors=True)
        raise GoogleDriveError("That backup file is damaged or not a Loonie backup.") from exc
    return staging


def _table_names(con: sqlite3.Connection) -> list[str]:
    return [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]


def _has_column(con: sqlite3.Connection, table: str, column: str) -> bool:
    return any(r[1] == column for r in con.execute(f'PRAGMA table_info("{table}")'))


def _adopt_for_account(user_id: str, staging: Path) -> None:
    """Makes the staged backup belong to `user_id`: drops anyone else's rows, or — when the
    backup came from a different single-owner install — re-labels it to this account. Statement
    paths and the statements folder layout are normalised to the per-account layout."""
    staged_db = staging / "lifeos.db"
    if not staged_db.exists():
        raise GoogleDriveError("This backup doesn't contain a Loonie database.")

    con = sqlite3.connect(str(staged_db))
    try:
        try:
            owners = [r[0] for r in con.execute("SELECT id FROM users")]
        except sqlite3.Error as exc:
            raise GoogleDriveError("This backup is not a valid Loonie database.") from exc
    finally:
        con.close()

    known_ids = set(owners) | {user_id}
    if user_id in owners:
        if len(owners) > 1:
            legacy_migration._prune_to_user(staged_db, user_id)  # noqa: SLF001
    elif len(owners) == 1:
        old_id = owners[0]
        con = sqlite3.connect(str(staged_db))
        try:
            for table in _table_names(con):
                if table != "users" and _has_column(con, table, "user_id"):
                    con.execute(f'UPDATE "{table}" SET user_id = ? WHERE user_id = ?', (user_id, old_id))
            con.execute("UPDATE users SET id = ? WHERE id = ?", (user_id, old_id))
            con.commit()
        finally:
            con.close()
    else:
        raise GoogleDriveError("This backup belongs to a different account and can't be restored here.")

    con = sqlite3.connect(str(staged_db))
    try:
        if "wealth_statement_imports" in _table_names(con):
            for row_id, stored in con.execute(
                "SELECT id, stored_path FROM wealth_statement_imports WHERE stored_path IS NOT NULL"
            ).fetchall():
                parts = Path(stored.replace("\\", "/")).parts
                rest: tuple[str, ...] | None = None
                if len(parts) >= 3 and parts[:2] == ("data", "statements") and parts[2] in known_ids:
                    rest = parts[3:]
                elif len(parts) >= 4 and parts[:2] == ("data", "users") and parts[2] in known_ids and parts[3] == "statements":
                    rest = parts[4:]
                if rest is not None:
                    new_path = Path("data", "users", user_id, "statements", *rest)
                    con.execute("UPDATE wealth_statement_imports SET stored_path = ? WHERE id = ?", (str(new_path), row_id))
            con.commit()
    finally:
        con.close()

    # Older backups nested statements one level deeper, under the owner's id.
    statements = staging / "statements"
    if statements.is_dir():
        nested = next((statements / n for n in known_ids if (statements / n).is_dir()), None)
        if nested is not None:
            holder = staging / "_statements_old"
            statements.rename(holder)
            (holder / nested.name).rename(staging / "statements")
            shutil.rmtree(holder, ignore_errors=True)


def _prune_safety_copies(folder: Path) -> None:
    """Keeps only the most recent pre-restore safety copy of the database and statements."""
    for pattern in ("lifeos.pre-restore-*.db", "statements.pre-restore-*"):
        copies = sorted(folder.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
        for old in copies[1:]:
            shutil.rmtree(old, ignore_errors=True) if old.is_dir() else old.unlink(missing_ok=True)


def _swap_in(user_id: str, staging: Path, before_attempt=None) -> None:
    """Moves the staged files into place. Raises OSError if Windows still has the database open."""
    folder = user_dir(user_id)
    db_path = user_db_path(user_id)
    stamp = int(time.time())

    def attempt(action) -> None:
        last: OSError | None = None
        for _ in range(8):
            try:
                if before_attempt:
                    before_attempt()
                action()
                return
            except OSError as exc:
                last = exc
                time.sleep(0.5)
        raise last  # type: ignore[misc]

    staged_db = staging / "lifeos.db"
    if staged_db.exists():
        if db_path.exists():
            attempt(lambda: db_path.rename(folder / f"lifeos.pre-restore-{stamp}.db"))
        for suffix in ("-wal", "-shm", "-journal"):
            db_path.with_name(db_path.name + suffix).unlink(missing_ok=True)
        staged_db.rename(db_path)

    staged_statements = staging / "statements"
    statements = folder / "statements"
    if staged_statements.exists():
        if statements.exists():
            attempt(lambda: statements.rename(folder / f"statements.pre-restore-{stamp}"))
        staged_statements.rename(statements)

    _prune_safety_copies(folder)


def restore_backup(user_id: str, file_id: str) -> str:
    """Restores this account from a Drive backup. Returns "restored" (done, no restart needed) or
    "restart_required" (staged; finishes when Loonie next starts)."""
    from app.database import dispose_user_engine
    from app.services.cloud_sync import _lock_for  # noqa: PLC2701

    staging = _download_and_extract(user_id, file_id)
    try:
        _adopt_for_account(user_id, staging)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    with _lock_for(user_id):  # pause cloud sync for this account while its files are swapped
        dispose_user_engine(user_id)
        try:
            _swap_in(user_id, staging, before_attempt=lambda: dispose_user_engine(user_id))
        except OSError as exc:
            log.warning("could not swap restore in live (%s); it will finish on next start", exc)
            (user_dir(user_id) / MARKER_NAME).write_text('{"staged": true}', encoding="utf-8")
            return "restart_required"

    shutil.rmtree(staging, ignore_errors=True)
    _refresh_profile(user_id)
    log.info("account %s restored from Google Drive backup", user_id)
    return "restored"


def _refresh_profile(user_id: str) -> None:
    """A backup made by another install carries that install's email/password; put this account's back."""
    from app.registry import Account, RegistrySession
    from app.services.accounts import provision_user_data

    with RegistrySession() as registry:
        account = registry.get(Account, user_id)
        if account is not None:
            provision_user_data(account)


def _apply_legacy_restore() -> None:
    """Handles a restore staged by an older version, before accounts had their own folders."""
    try:
        db_path = get_database_path()
        staged_db = _LEGACY_STAGING / db_path.name
        if staged_db.exists():
            if db_path.exists():
                shutil.move(str(db_path), str(db_path.with_name(f"{db_path.stem}.pre-restore-{int(time.time())}{db_path.suffix}")))
            shutil.move(str(staged_db), str(db_path))
        staged_statements = _LEGACY_STAGING / "statements"
        statements_dir = DATA_DIR / "statements"
        if staged_statements.exists():
            if statements_dir.exists():
                shutil.rmtree(statements_dir)
            shutil.move(str(staged_statements), str(statements_dir))
    finally:
        shutil.rmtree(_LEGACY_STAGING, ignore_errors=True)
        _LEGACY_MARKER.unlink(missing_ok=True)


def apply_pending_restore_if_any() -> None:
    """Startup hook, before any database is opened: finishes restores that couldn't be applied live."""
    if _LEGACY_MARKER.exists():
        _apply_legacy_restore()
    if not USERS_DIR.exists():
        return
    for folder in USERS_DIR.iterdir():
        marker = folder / MARKER_NAME
        if not marker.exists():
            continue
        try:
            _swap_in(folder.name, folder / STAGING_NAME)
            log.info("restored account %s from Google Drive backup", folder.name)
        except Exception:  # noqa: BLE001 - never block startup on a bad restore
            log.exception("restore failed for account %s", folder.name)
            continue
        shutil.rmtree(folder / STAGING_NAME, ignore_errors=True)
        marker.unlink(missing_ok=True)
