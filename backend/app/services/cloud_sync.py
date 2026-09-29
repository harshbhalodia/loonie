"""Loonie Cloud sync client.

Each account can link itself to a cloud workspace. Once linked, local changes are pushed in the
background within seconds, and changes made on other devices are pulled every ~30 s — the same
model as Postman's workspace sync. The local database stays the working copy, so the app keeps
working offline and catches up on reconnect.

Link state (server address, token, device id, last sync) lives in the account's own folder
(`cloud.json`), so linking one account never affects another.
"""
from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from datetime import datetime, timezone
from urllib.parse import urlparse

import httpx

from app.config import get_cloud_config, user_dir
from app.database import get_user_engine
from app.registry import Account, RegistrySession
from app.services import sync_engine

log = logging.getLogger("loonie.cloud")

PUSH_BATCH = 300
PULL_BATCH = 500
POLL_SECONDS = 30
TICK_SECONDS = 5
TOKEN_REFRESH_SECONDS = 7 * 24 * 3600
# Rows a brand-new account always has; they don't count as "existing data" when deciding whether
# a device should adopt a cloud workspace outright.
_SEEDED_TABLES = ("wealth_category_groups",)


class CloudError(RuntimeError):
    pass


_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()
_syncing: set[str] = set()
_last_poll: dict[str, float] = {}
_failures: dict[str, int] = {}
_next_attempt: dict[str, float] = {}
_stop = threading.Event()
_worker: threading.Thread | None = None


def _lock_for(user_id: str) -> threading.Lock:
    with _locks_guard:
        return _locks.setdefault(user_id, threading.Lock())


# ---------------------------------------------------------------------------
# Per-account link state
# ---------------------------------------------------------------------------

def _state_path(user_id: str):
    return user_dir(user_id) / "cloud.json"


def load_state(user_id: str) -> dict:
    path = _state_path(user_id)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_state(user_id: str, state: dict) -> None:
    path = _state_path(user_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state), encoding="utf-8")
    tmp.replace(path)


def configured_base_url() -> str:
    return str(get_cloud_config().get("base_url") or "").strip().rstrip("/")


def validate_base_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise CloudError("The cloud server address must start with https:// (or http:// for localhost).")
    if parsed.scheme == "http" and parsed.hostname not in ("localhost", "127.0.0.1", "::1"):
        raise CloudError("Use an https:// address — credentials must not be sent over plain http.")
    return url.rstrip("/")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _detail(resp: httpx.Response) -> str:
    try:
        body = resp.json()
        if isinstance(body, dict) and "detail" in body:
            return str(body["detail"])
    except ValueError:
        pass
    return f"cloud returned HTTP {resp.status_code}"


def _request(client: httpx.Client, method: str, path: str, **kwargs) -> dict:
    try:
        resp = client.request(method, path, **kwargs)
    except httpx.HTTPError as exc:
        raise CloudError(f"Could not reach Loonie Cloud ({exc.__class__.__name__}).") from exc
    if resp.status_code == 401:
        raise AuthExpired(_detail(resp))
    if resp.status_code >= 400:
        raise CloudError(_detail(resp))
    return resp.json()


class AuthExpired(CloudError):
    pass


def _client(base_url: str, token: str | None = None) -> httpx.Client:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return httpx.Client(base_url=base_url, headers=headers, timeout=60)


# ---------------------------------------------------------------------------
# Public API used by the router
# ---------------------------------------------------------------------------

def status(user_id: str) -> dict:
    state = load_state(user_id)
    connected = bool(state.get("token"))
    pending = 0
    if connected:
        pending = sync_engine.pending_count(get_user_engine(user_id))
    return {
        "configured": bool(configured_base_url()),
        "base_url": state.get("base_url") or configured_base_url(),
        "connected": connected,
        "email": state.get("email"),
        "last_sync_at": state.get("last_sync_at"),
        "last_error": state.get("last_error"),
        "auth_expired": bool(state.get("auth_expired")),
        "pending_changes": pending,
        "syncing": user_id in _syncing,
    }


def connect(user_id: str, mode: str, email: str, password: str, strategy: str | None) -> dict:
    """Signs in to (or registers on) the cloud and links this account to its workspace."""
    base_url = validate_base_url(configured_base_url()) if configured_base_url() else ""
    if not base_url:
        raise CloudError("No cloud server address is configured.")

    with _client(base_url) as anon:
        auth = _request(anon, "POST", f"/v1/auth/{'register' if mode == 'register' else 'login'}",
                        json={"email": email, "password": password})
    token = auth["access_token"]

    with _client(base_url, token) as client:
        summary = _request(client, "GET", "/v1/sync/summary")

    engine = get_user_engine(user_id)
    cloud_records = int(summary.get("record_count", 0))
    local_records = sync_engine.count_local_rows(engine, exclude=_SEEDED_TABLES)
    previous = load_state(user_id)
    # Same workspace as before (e.g. the session simply expired): keep our sync position.
    resume = bool(previous.get("device_id")) and previous.get("workspace_id") == auth.get("workspace_id")

    if resume:
        plan = "resume"
    elif cloud_records == 0:
        plan = "upload"
    elif local_records == 0:
        plan = "replace"
    elif strategy in ("merge", "replace"):
        plan = strategy
    else:
        return {"status": "needs_choice", "cloud_records": cloud_records, "local_records": local_records}

    with _lock_for(user_id):
        if plan == "replace":
            sync_engine.wipe_synced_data(engine)
        elif plan != "resume":
            sync_engine.reset_sync_position(engine)
            sync_engine.seed_all_local_changes(engine)
        _save_state(user_id, {
            "base_url": base_url,
            "token": token,
            "token_at": time.time(),
            "email": auth.get("email", email),
            "workspace_id": auth.get("workspace_id"),
            "device_id": previous.get("device_id") or str(uuid.uuid4()),
            "connected_at": previous.get("connected_at") or _now_iso(),
            "last_sync_at": previous.get("last_sync_at"),
            "last_error": None,
        })
    log.info("account %s linked to cloud workspace %s (%s)", user_id, auth.get("workspace_id"), plan)

    sync_now(user_id)
    return {"status": "connected", "plan": plan}


def disconnect(user_id: str) -> None:
    """Unlinks this account. Local data is kept untouched."""
    with _lock_for(user_id):
        _state_path(user_id).unlink(missing_ok=True)
        sync_engine.reset_sync_position(get_user_engine(user_id))
    log.info("account %s unlinked from cloud", user_id)


# ---------------------------------------------------------------------------
# Sync
# ---------------------------------------------------------------------------

def sync_now(user_id: str) -> None:
    """One full push + pull cycle. Raises CloudError on failure (also recorded on the link)."""
    state = load_state(user_id)
    if not state.get("token"):
        raise CloudError("This account is not linked to Loonie Cloud.")

    lock = _lock_for(user_id)
    if not lock.acquire(blocking=False):
        return  # a sync is already running
    _syncing.add(user_id)
    try:
        engine = get_user_engine(user_id)
        try:
            with _client(state["base_url"], state["token"]) as client:
                if time.time() - state.get("token_at", 0) > TOKEN_REFRESH_SECONDS:
                    try:
                        refreshed = _request(client, "POST", "/v1/auth/refresh")
                        state["token"], state["token_at"] = refreshed["access_token"], time.time()
                        client.headers["Authorization"] = f"Bearer {state['token']}"
                    except CloudError:
                        pass  # keep using the current token; a real 401 is handled below

                pushed = _push(client, engine, user_id, state["device_id"])
                pulled = _pull(client, engine, user_id, state["device_id"])
            state.update(last_sync_at=_now_iso(), last_error=None, auth_expired=False)
            if pushed or pulled:
                log.info("cloud sync for %s: pushed %d, pulled %d", user_id, pushed, pulled)
        except AuthExpired as exc:
            state.update(last_error="Your cloud session expired. Sign in to Loonie Cloud again.", auth_expired=True)
            _save_state(user_id, state)
            raise CloudError(state["last_error"]) from exc
        except CloudError as exc:
            state["last_error"] = str(exc)
            _save_state(user_id, state)
            raise
        _save_state(user_id, state)
    finally:
        _syncing.discard(user_id)
        lock.release()


def _push(client: httpx.Client, engine, user_id: str, device_id: str) -> int:
    total = 0
    while True:
        records, max_seq = sync_engine.collect_pending(engine, user_id, PUSH_BATCH)
        if max_seq == 0:
            return total
        if records:
            _request(client, "POST", "/v1/sync/push", json={"device_id": device_id, "records": records})
            total += len(records)
        sync_engine.mark_pushed(engine, max_seq)


def _pull(client: httpx.Client, engine, user_id: str, device_id: str) -> int:
    total = 0
    since = sync_engine.get_state(engine)["last_pulled_rev"]
    while True:
        page = _request(client, "GET", "/v1/sync/pull",
                        params={"since": since, "device_id": device_id, "limit": PULL_BATCH})
        records = page.get("records", [])
        if records:
            applied, _skipped = sync_engine.apply_remote(engine, records, user_id)
            total += applied
        has_more = bool(page.get("has_more"))
        since = records[-1]["rev"] if (has_more and records) else int(page.get("latest_rev", since))
        sync_engine.set_last_pulled_rev(engine, since)
        if not has_more:
            return total


# ---------------------------------------------------------------------------
# Background worker
# ---------------------------------------------------------------------------

def _tick() -> None:
    with RegistrySession() as registry:
        user_ids = [a.id for a in registry.query(Account).all()]
    now = time.time()
    for user_id in user_ids:
        state = load_state(user_id)
        if not state.get("token") or state.get("auth_expired") or now < _next_attempt.get(user_id, 0):
            continue
        engine = get_user_engine(user_id)
        due = now - _last_poll.get(user_id, 0) >= POLL_SECONDS
        if not due and sync_engine.pending_count(engine) == 0:
            continue
        try:
            sync_now(user_id)
            _failures.pop(user_id, None)
            _next_attempt.pop(user_id, None)
        except CloudError as exc:
            failures = _failures.get(user_id, 0) + 1
            _failures[user_id] = failures
            _next_attempt[user_id] = time.time() + min(300, TICK_SECONDS * 2**failures)
            log.warning("cloud sync failed for %s (attempt %d): %s", user_id, failures, exc)
        finally:
            _last_poll[user_id] = time.time()


def _worker_loop() -> None:
    while not _stop.is_set():
        try:
            _tick()
        except Exception:  # noqa: BLE001 - the sync loop must never die
            log.exception("sync worker error")
        _stop.wait(TICK_SECONDS)


def start_worker() -> None:
    global _worker
    if _worker and _worker.is_alive():
        return
    _stop.clear()
    _worker = threading.Thread(target=_worker_loop, name="cloud-sync-worker", daemon=True)
    _worker.start()


def stop_worker() -> None:
    _stop.set()
