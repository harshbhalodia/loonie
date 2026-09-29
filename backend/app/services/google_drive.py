"""Google Drive backup/restore for an account's own data folder (database + statement PDFs).

Every account connects and backs up separately: its Drive token, backups and restore staging all
live inside that account's folder (`backend/data/users/<id>/`).

Uses the narrow `drive.file` OAuth scope (the app can only see files it created itself) and a
hand-rolled Authorization Code + PKCE loopback flow — no Google client SDK needed, just httpx,
matching this codebase's existing "raw httpx client" pattern (see jev_client.py/ai_provider.py).

Nothing here is wired to any endpoint requiring the frontend to hold Google credentials — the
backend is the only thing that ever talks to Google, consistent with the rest of the app.
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import re
import secrets
import shutil
import sqlite3
import threading
import time
import uuid
import webbrowser
import zipfile
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

from app.config import get_custom_google_drive_config, get_google_drive_config, user_db_path, user_dir

log = logging.getLogger("loonie.drive")

SCOPE = "https://www.googleapis.com/auth/drive.file"
AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
DRIVE_FILES_ENDPOINT = "https://www.googleapis.com/drive/v3/files"
DRIVE_UPLOAD_ENDPOINT = "https://www.googleapis.com/upload/drive/v3/files"
BACKUP_FOLDER_NAME = "Loonie Backups"

_oauth_lock = threading.Lock()
# Per-account connect progress: idle | connecting | connected | error
_oauth_state: dict[str, dict] = {}


class GoogleDriveError(RuntimeError):
    pass


def _token_path(user_id: str) -> Path:
    return user_dir(user_id) / "google_drive_token.json"


def _backup_prefix(user_id: str) -> str:
    return f"loonie-backup-{user_id[:8]}-"


# ---------------------------------------------------------------------------
# Token storage
# ---------------------------------------------------------------------------

def _load_token(user_id: str) -> dict | None:
    path = _token_path(user_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _save_token(user_id: str, token: dict) -> None:
    path = _token_path(user_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(token), encoding="utf-8")


def is_connected(user_id: str) -> bool:
    return _load_token(user_id) is not None


def disconnect(user_id: str) -> None:
    _token_path(user_id).unlink(missing_ok=True)
    with _oauth_lock:
        _oauth_state[user_id] = {"status": "idle", "error": None}


def get_status(user_id: str) -> dict:
    cfg = get_google_drive_config()
    with _oauth_lock:
        state = _oauth_state.get(user_id, {"status": "idle", "error": None})
        oauth_status, error = state["status"], state["error"]
    return {
        "configured": bool(cfg.get("client_id") and cfg.get("client_secret")),
        "custom_client": bool(get_custom_google_drive_config().get("client_id")),
        "connected": is_connected(user_id),
        "connecting": oauth_status == "connecting",
        "error": error,
    }


# ---------------------------------------------------------------------------
# OAuth connect flow (Authorization Code + PKCE, local loopback redirect)
# ---------------------------------------------------------------------------

class _CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 - required BaseHTTPRequestHandler name
        self.server.oauth_result = parse_qs(urlparse(self.path).query)  # type: ignore[attr-defined]
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(b"<html><body><h3>Loonie connected to Google Drive</h3>"
                          b"<p>You can close this tab and return to Loonie.</p></body></html>")

    def log_message(self, format: str, *args) -> None:  # noqa: A002 - silence default stderr logging
        pass


def start_connect(user_id: str) -> None:
    cfg = get_google_drive_config()
    if not cfg.get("client_id") or not cfg.get("client_secret"):
        raise GoogleDriveError("Google Drive backup isn't set up in this version of Loonie yet.")

    with _oauth_lock:
        if _oauth_state.get(user_id, {}).get("status") == "connecting":
            return
        _oauth_state[user_id] = {"status": "connecting", "error": None}

    thread = threading.Thread(target=_run_oauth_flow, args=(user_id, dict(cfg)), daemon=True)
    thread.start()


def _run_oauth_flow(user_id: str, cfg: dict) -> None:
    try:
        client_id = cfg["client_id"]
        client_secret = cfg["client_secret"]
        verifier = secrets.token_urlsafe(64)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        state = secrets.token_urlsafe(16)

        server = HTTPServer(("127.0.0.1", 0), _CallbackHandler)
        server.timeout = 300
        server.oauth_result = None  # type: ignore[attr-defined]
        port = server.server_address[1]
        redirect_uri = f"http://127.0.0.1:{port}/"

        auth_url = AUTH_ENDPOINT + "?" + urlencode({
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": SCOPE,
            "access_type": "offline",
            "prompt": "consent",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": state,
        })

        webbrowser.open(auth_url)
        deadline = time.time() + 300
        while time.time() < deadline and server.oauth_result is None:  # type: ignore[attr-defined]
            server.handle_request()
        server.server_close()

        result = server.oauth_result  # type: ignore[attr-defined]
        if not result or "code" not in result:
            raise GoogleDriveError("Google sign-in was cancelled or timed out.")
        if result.get("state", [None])[0] != state:
            raise GoogleDriveError("OAuth state mismatch, please try connecting again.")

        response = httpx.post(TOKEN_ENDPOINT, data={
            "client_id": client_id,
            "client_secret": client_secret,
            "code": result["code"][0],
            "code_verifier": verifier,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        }, timeout=30)
        response.raise_for_status()
        token = response.json()
        token["obtained_at"] = time.time()
        _save_token(user_id, token)

        with _oauth_lock:
            _oauth_state[user_id] = {"status": "connected", "error": None}
    except Exception as exc:  # noqa: BLE001 - surfaced to the user via /status, not raised
        log.warning("Google Drive connect failed: %s", exc)
        with _oauth_lock:
            _oauth_state[user_id] = {"status": "error", "error": str(exc)}


def _get_access_token(user_id: str) -> str:
    token = _load_token(user_id)
    if not token:
        raise GoogleDriveError("Google Drive is not connected.")

    if time.time() < token.get("obtained_at", 0) + token.get("expires_in", 3600) - 60:
        return token["access_token"]

    cfg = get_google_drive_config()
    response = httpx.post(TOKEN_ENDPOINT, data={
        "client_id": cfg.get("client_id"),
        "client_secret": cfg.get("client_secret"),
        "refresh_token": token.get("refresh_token"),
        "grant_type": "refresh_token",
    }, timeout=30)
    response.raise_for_status()
    refreshed = response.json()
    token["access_token"] = refreshed["access_token"]
    token["expires_in"] = refreshed.get("expires_in", 3600)
    token["obtained_at"] = time.time()
    _save_token(user_id, token)
    return token["access_token"]


# ---------------------------------------------------------------------------
# Drive REST helpers
# ---------------------------------------------------------------------------

def _ensure_backup_folder(access_token: str) -> str:
    headers = {"Authorization": f"Bearer {access_token}"}
    query = "name='%s' and mimeType='application/vnd.google-apps.folder' and trashed=false" % BACKUP_FOLDER_NAME
    resp = httpx.get(DRIVE_FILES_ENDPOINT, headers=headers, params={"q": query, "fields": "files(id,name)"}, timeout=30)
    resp.raise_for_status()
    files = resp.json().get("files", [])
    if files:
        return files[0]["id"]

    resp = httpx.post(
        DRIVE_FILES_ENDPOINT,
        headers=headers,
        json={"name": BACKUP_FOLDER_NAME, "mimeType": "application/vnd.google-apps.folder"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["id"]


def _build_multipart_body(boundary: str, metadata: dict, media: bytes, media_type: str) -> bytes:
    head = f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n{json.dumps(metadata)}\r\n"
    media_head = f"--{boundary}\r\nContent-Type: {media_type}\r\n\r\n"
    return head.encode() + media_head.encode() + media + f"\r\n--{boundary}--".encode()


def _build_backup_zip(user_id: str) -> Path:
    """Snapshots the account's DB via sqlite3's own backup API (avoids zipping a file mid-write),
    plus its statements folder, into one zip inside the account's folder."""
    folder = user_dir(user_id)
    staging = folder / f"_backup_staging_{uuid.uuid4().hex}"
    staging.mkdir(parents=True, exist_ok=True)
    try:
        db_path = user_db_path(user_id)
        if db_path.exists():
            snapshot_path = staging / "lifeos.db"
            src_conn = sqlite3.connect(str(db_path))
            dst_conn = sqlite3.connect(str(snapshot_path))
            with dst_conn:
                src_conn.backup(dst_conn)
            src_conn.close()
            dst_conn.close()

        statements_dir = folder / "statements"
        if statements_dir.exists():
            shutil.copytree(statements_dir, staging / "statements")

        zip_path = folder / f"{_backup_prefix(user_id)}{datetime.now().strftime('%Y%m%d-%H%M%S')}.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for file in staging.rglob("*"):
                if file.is_file():
                    zf.write(file, file.relative_to(staging))
        return zip_path
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def create_backup(user_id: str) -> dict:
    cfg = get_google_drive_config()
    if not cfg.get("enabled", False):
        raise GoogleDriveError("Google Drive backup isn't available right now.")

    access_token = _get_access_token(user_id)
    folder_id = _ensure_backup_folder(access_token)
    zip_path = _build_backup_zip(user_id)
    try:
        boundary = uuid.uuid4().hex
        body = _build_multipart_body(
            boundary, {"name": zip_path.name, "parents": [folder_id]}, zip_path.read_bytes(), "application/zip"
        )
        resp = httpx.post(
            DRIVE_UPLOAD_ENDPOINT,
            params={"uploadType": "multipart", "fields": "id,name,createdTime,size"},
            headers={"Authorization": f"Bearer {access_token}", "Content-Type": f"multipart/related; boundary={boundary}"},
            content=body,
            timeout=120,
        )
        resp.raise_for_status()
        log.info("Google Drive backup uploaded for account %s", user_id)
        return resp.json()
    finally:
        zip_path.unlink(missing_ok=True)


_LEGACY_BACKUP_NAME = re.compile(r"^loonie-backup-\d{8}-\d{6}\.zip$")


def list_backups(user_id: str) -> list[dict]:
    access_token = _get_access_token(user_id)
    folder_id = _ensure_backup_folder(access_token)
    resp = httpx.get(
        DRIVE_FILES_ENDPOINT,
        headers={"Authorization": f"Bearer {access_token}"},
        params={"q": f"'{folder_id}' in parents and trashed=false", "fields": "files(id,name,createdTime,size)", "orderBy": "createdTime desc"},
        timeout=30,
    )
    resp.raise_for_status()
    prefix = _backup_prefix(user_id)
    # Backups made before per-account folders have no account tag; they stay visible.
    return [
        f for f in resp.json().get("files", [])
        if f["name"].startswith(prefix) or _LEGACY_BACKUP_NAME.match(f["name"])
    ]

