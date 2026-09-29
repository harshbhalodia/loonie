"""Change tracking + row-level apply for cloud sync, done entirely inside each account's SQLite
file so no router or model needs to know sync exists.

How it works:
  * SQLite triggers on every synced table append (table, row id, timestamp) to `sync_changes`
    whenever a row is inserted/updated/deleted — unless `sync_state.applying` is set, which is how
    rows arriving FROM the cloud are applied without echoing straight back.
  * The sync worker reads the current state of each changed row and pushes it; pulled rows are
    written with a raw upsert. Conflicts resolve last-writer-wins on the change timestamp.

The bookkeeping tables are created at runtime (not via Alembic) so triggers can be re-installed on
every start and automatically cover tables added by future migrations.
"""
from __future__ import annotations

import logging
import time
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

log = logging.getLogger("loonie.sync")

# Tables that are local-only: credentials, machine-specific work queues, and per-install licences.
EXCLUDED_TABLES = {"users", "wealth_jobs", "marketplace_installed_blueprints", "alembic_version"}

_NOW_MS = "CAST((julianday('now') - 2440587.5) * 86400000 AS INTEGER)"

# Every row carries its local account id in `user_id`. On the wire that id is replaced by this
# placeholder, so the same cloud workspace can be opened by a different local account on another
# device (whose id differs) and still see all of its data.
OWNER_TOKEN = "@owner"


def _q(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def now_ms() -> int:
    return int(time.time() * 1000)


def _table_columns(conn, table: str) -> list[str]:
    return [row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info({_q(table)})").fetchall()]


def synced_tables(engine: Engine) -> list[str]:
    with engine.connect() as conn:
        names = [
            r[0]
            for r in conn.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            ).fetchall()
        ]
        return [
            n for n in names if n not in EXCLUDED_TABLES and not n.startswith("sync_") and "id" in _table_columns(conn, n)
        ]


def install(engine: Engine) -> None:
    """Creates bookkeeping tables and (re)installs change-tracking triggers. Idempotent."""
    tables = synced_tables(engine)
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "CREATE TABLE IF NOT EXISTS sync_changes ("
            "seq INTEGER PRIMARY KEY AUTOINCREMENT, tbl TEXT NOT NULL, row_id TEXT NOT NULL, ts INTEGER NOT NULL)"
        )
        conn.exec_driver_sql(
            "CREATE TABLE IF NOT EXISTS sync_state ("
            "id INTEGER PRIMARY KEY CHECK (id = 1), applying INTEGER NOT NULL DEFAULT 0, "
            "last_pushed_seq INTEGER NOT NULL DEFAULT 0, last_pulled_rev INTEGER NOT NULL DEFAULT 0)"
        )
        conn.exec_driver_sql("INSERT OR IGNORE INTO sync_state (id) VALUES (1)")
        conn.exec_driver_sql("UPDATE sync_state SET applying = 0")

        for table in tables:
            for suffix in ("ai", "au", "ad"):
                conn.exec_driver_sql(f"DROP TRIGGER IF EXISTS {_q(f'sync_{table}_{suffix}')}")
            guard = "WHEN (SELECT applying FROM sync_state WHERE id = 1) = 0"
            for suffix, event, ref in (("ai", "INSERT", "NEW"), ("au", "UPDATE", "NEW"), ("ad", "DELETE", "OLD")):
                conn.exec_driver_sql(
                    f"CREATE TRIGGER {_q(f'sync_{table}_{suffix}')} AFTER {event} ON {_q(table)} {guard} "
                    f"BEGIN INSERT INTO sync_changes (tbl, row_id, ts) VALUES ('{table}', {ref}.id, {_NOW_MS}); END"
                )
    log.info("sync change-tracking installed on %d tables", len(tables))


# ---------------------------------------------------------------------------
# State / counters
# ---------------------------------------------------------------------------

def get_state(engine: Engine) -> dict[str, int]:
    with engine.connect() as conn:
        row = conn.exec_driver_sql("SELECT last_pushed_seq, last_pulled_rev FROM sync_state WHERE id = 1").fetchone()
    return {"last_pushed_seq": row[0], "last_pulled_rev": row[1]}


def set_last_pulled_rev(engine: Engine, rev: int) -> None:
    with engine.begin() as conn:
        conn.execute(text("UPDATE sync_state SET last_pulled_rev = :r WHERE id = 1"), {"r": rev})


def pending_count(engine: Engine) -> int:
    with engine.connect() as conn:
        return conn.exec_driver_sql(
            "SELECT COUNT(*) FROM (SELECT 1 FROM sync_changes "
            "WHERE seq > (SELECT last_pushed_seq FROM sync_state WHERE id = 1) GROUP BY tbl, row_id)"
        ).scalar_one()


def count_local_rows(engine: Engine, exclude: tuple[str, ...] = ()) -> int:
    total = 0
    with engine.connect() as conn:
        for table in synced_tables(engine):
            if table in exclude:
                continue
            total += conn.exec_driver_sql(f"SELECT COUNT(*) FROM {_q(table)}").scalar_one()
    return total


# ---------------------------------------------------------------------------
# Push side
# ---------------------------------------------------------------------------

def collect_pending(engine: Engine, owner_id: str, limit: int = 300) -> tuple[list[dict[str, Any]], int]:
    """Returns (records, max_seq). Each record is the row's CURRENT state (or a delete marker)."""
    valid = set(synced_tables(engine))
    records: list[dict[str, Any]] = []
    max_seq = 0
    with engine.connect() as conn:
        groups = conn.exec_driver_sql(
            "SELECT tbl, row_id, MAX(seq), MAX(ts) FROM sync_changes "
            "WHERE seq > (SELECT last_pushed_seq FROM sync_state WHERE id = 1) "
            "GROUP BY tbl, row_id ORDER BY MAX(seq) LIMIT ?",
            (limit,),
        ).fetchall()
        for tbl, row_id, seq, ts in groups:
            max_seq = max(max_seq, seq)
            if tbl not in valid:
                continue
            row = conn.exec_driver_sql(f"SELECT * FROM {_q(tbl)} WHERE id = ?", (row_id,)).mappings().first()
            if row is None:
                records.append({"table": tbl, "id": row_id, "op": "delete", "data": None, "client_ts": ts})
            else:
                data = dict(row)
                if data.get("user_id") == owner_id:
                    data["user_id"] = OWNER_TOKEN
                records.append({"table": tbl, "id": row_id, "op": "upsert", "data": data, "client_ts": ts})
    return records, max_seq


def mark_pushed(engine: Engine, max_seq: int) -> None:
    with engine.begin() as conn:
        conn.execute(text("UPDATE sync_state SET last_pushed_seq = :s WHERE id = 1 AND last_pushed_seq < :s"), {"s": max_seq})
        conn.execute(text("DELETE FROM sync_changes WHERE seq <= :s"), {"s": max_seq})


def seed_all_local_changes(engine: Engine) -> int:
    """Queues every existing row for upload (used when first connecting a device with data)."""
    count = 0
    with engine.begin() as conn:
        for table in synced_tables(engine):
            result = conn.exec_driver_sql(
                f"INSERT INTO sync_changes (tbl, row_id, ts) SELECT '{table}', id, {_NOW_MS} FROM {_q(table)}"
            )
            count += result.rowcount or 0
    return count


# ---------------------------------------------------------------------------
# Pull side
# ---------------------------------------------------------------------------

def apply_remote(engine: Engine, records: list[dict[str, Any]], owner_id: str) -> tuple[int, int]:
    """Writes records received from the cloud. Returns (applied, skipped)."""
    valid = set(synced_tables(engine))
    applied = skipped = 0
    with engine.begin() as conn:
        conn.exec_driver_sql("UPDATE sync_state SET applying = 1")
        try:
            columns_cache: dict[str, set[str]] = {}
            for rec in records:
                table, row_id = rec.get("table"), rec.get("id")
                if table not in valid or not isinstance(row_id, str):
                    skipped += 1
                    continue
                # A newer local edit that hasn't been pushed yet wins over an older remote change.
                newer_local = conn.exec_driver_sql(
                    "SELECT 1 FROM sync_changes WHERE tbl = ? AND row_id = ? AND ts > ? "
                    "AND seq > (SELECT last_pushed_seq FROM sync_state WHERE id = 1) LIMIT 1",
                    (table, row_id, int(rec.get("client_ts") or 0)),
                ).first()
                if newer_local:
                    skipped += 1
                    continue

                if rec.get("op") == "delete":
                    conn.exec_driver_sql(f"DELETE FROM {_q(table)} WHERE id = ?", (row_id,))
                    applied += 1
                    continue

                cols = columns_cache.setdefault(table, set(_table_columns(conn, table)))
                data = {k: v for k, v in (rec.get("data") or {}).items() if k in cols}
                if data.get("user_id") == OWNER_TOKEN:
                    data["user_id"] = owner_id
                if data.get("id") != row_id:
                    skipped += 1
                    continue
                names = list(data)
                try:
                    conn.exec_driver_sql(
                        f"INSERT OR REPLACE INTO {_q(table)} ({', '.join(_q(n) for n in names)}) "
                        f"VALUES ({', '.join('?' for _ in names)})",
                        tuple(data[n] for n in names),
                    )
                    applied += 1
                except Exception as exc:  # noqa: BLE001 - one bad row must not block the rest
                    log.warning("could not apply remote row %s/%s: %s", table, row_id, exc)
                    skipped += 1
        finally:
            conn.exec_driver_sql("UPDATE sync_state SET applying = 0")
    return applied, skipped


def wipe_synced_data(engine: Engine) -> None:
    """Empties every synced table without recording deletions (used before adopting cloud data)."""
    with engine.begin() as conn:
        conn.exec_driver_sql("UPDATE sync_state SET applying = 1")
        try:
            for table in synced_tables(engine):
                conn.exec_driver_sql(f"DELETE FROM {_q(table)}")
            conn.exec_driver_sql("DELETE FROM sync_changes")
            conn.exec_driver_sql("UPDATE sync_state SET last_pushed_seq = 0, last_pulled_rev = 0")
        finally:
            conn.exec_driver_sql("UPDATE sync_state SET applying = 0")


def reset_sync_position(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.exec_driver_sql("DELETE FROM sync_changes")
        conn.exec_driver_sql("UPDATE sync_state SET last_pushed_seq = 0, last_pulled_rev = 0")
