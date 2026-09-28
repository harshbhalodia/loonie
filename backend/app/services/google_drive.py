"""Google Drive backup/restore for the local database + statement PDFs.

Uses the narrow `drive.file` OAuth scope (the app can only see files it created itself) and a
hand-rolled Authorization Code + PKCE loopback flow — no Google client SDK needed, just httpx,
matching this codebase's existing "raw httpx client" pattern (see jev_client.py/ai_provider.py).

Nothing here is wired to any endpoint requiring the frontend to hold Google credentials — the
backend is the only thing that ever talks to Google, consistent with the rest of the app.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
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

from app.config import BACKEND_DIR, get_database_path, get_google_drive_config

DATA_DIR = BACKEND_DIR / "data"
TOKEN_PATH = DATA_DIR / "google_drive_token.json"
RESTORE_STAGING_DIR = DATA_DIR / "_pending_restore"
PENDING_RESTORE_MARKER = DATA_DIR / ".pending_restore.json"

SCOPE = "https://www.googleapis.com/auth/drive.file"
AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
DRIVE_FILES_ENDPOINT = "https://www.googleapis.com/drive/v3/files"
DRIVE_UPLOAD_ENDPOINT = "https://www.googleapis.com/upload/drive/v3/files"
BACKUP_FOLDER_NAME = "Loonie Backups"

_oauth_lock = threading.Lock()
_oauth_state: dict = {"status": "idle", "error": None}  # idle | connecting | connected | error


class GoogleDriveError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# Token storage
# ---------------------------------------------------------------------------

def _load_token() -> dict | None:
    if not TOKEN_PATH.exists():
        return None
    try:
        return json.loads(TOKEN_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _save_token(token: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    TOKEN_PATH.write_text(json.dumps(token), encoding="utf-8")


def is_connected() -> bool:
    return _load_token() is not None


def disconnect() -> None:
    TOKEN_PATH.unlink(missing_ok=True)
    with _oauth_lock:
        _oauth_state["status"] = "idle"
        _oauth_state["error"] = None


def get_status() -> dict:
    cfg = get_google_drive_config()
    with _oauth_lock:
        oauth_status, error = _oauth_state["status"], _oauth_state["error"]
    return {
        "configured": bool(cfg.get("client_id") and cfg.get("client_secret")),
        "connected": is_connected(),
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


def start_connect() -> None:
    cfg = get_google_drive_config()
    if not cfg.get("client_id") or not cfg.get("client_secret"):
        raise GoogleDriveError("Add your Google OAuth client ID and secret under Settings → Google Drive backup first.")

    with _oauth_lock:
        if _oauth_state["status"] == "connecting":
            return
        _oauth_state["status"] = "connecting"
        _oauth_state["error"] = None

    thread = threading.Thread(target=_run_oauth_flow, args=(dict(cfg),), daemon=True)
    thread.start()


def _run_oauth_flow(cfg: dict) -> None:
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
        _save_token(token)

        with _oauth_lock:
            _oauth_state["status"] = "connected"
            _oauth_state["error"] = None
    except Exception as exc:  # noqa: BLE001 - surfaced to the user via /status, not raised
        with _oauth_lock:
            _oauth_state["status"] = "error"
            _oauth_state["error"] = str(exc)


def _get_access_token() -> str:
    token = _load_token()
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
    _save_token(token)
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


def _build_backup_zip() -> Path:
    """Snapshots the DB via sqlite3's own backup API (avoids zipping a file mid-write), plus
    the statements folder, into one zip under backend/data/."""
    staging = DATA_DIR / f"_backup_staging_{uuid.uuid4().hex}"
    staging.mkdir(parents=True, exist_ok=True)
    try:
        db_path = get_database_path()
        if db_path.exists():
            snapshot_path = staging / db_path.name
            src_conn = sqlite3.connect(str(db_path))
            dst_conn = sqlite3.connect(str(snapshot_path))
            with dst_conn:
                src_conn.backup(dst_conn)
            src_conn.close()
            dst_conn.close()

        statements_dir = DATA_DIR / "statements"
        if statements_dir.exists():
            shutil.copytree(statements_dir, staging / "statements")

        zip_path = DATA_DIR / f"loonie-backup-{datetime.now().strftime('%Y%m%d-%H%M%S')}.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for file in staging.rglob("*"):
                if file.is_file():
                    zf.write(file, file.relative_to(staging))
        return zip_path
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def create_backup() -> dict:
    cfg = get_google_drive_config()
    if not cfg.get("enabled", False):
        raise GoogleDriveError("Google Drive backup is turned off. Enable it under Settings → Google Drive backup.")

    access_token = _get_access_token()
    folder_id = _ensure_backup_folder(access_token)
    zip_path = _build_backup_zip()
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
        return resp.json()
    finally:
        zip_path.unlink(missing_ok=True)


def list_backups() -> list[dict]:
    access_token = _get_access_token()
    folder_id = _ensure_backup_folder(access_token)
    resp = httpx.get(
        DRIVE_FILES_ENDPOINT,
        headers={"Authorization": f"Bearer {access_token}"},
        params={"q": f"'{folder_id}' in parents and trashed=false", "fields": "files(id,name,createdTime,size)", "orderBy": "createdTime desc"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json().get("files", [])


def stage_restore(file_id: str) -> None:
    """Downloads + extracts the chosen backup into a staging dir and drops a marker file.
    The actual swap happens on next startup (`apply_pending_restore_if_any`), before the DB
    engine ever opens a connection, so there's no SQLite file-lock conflict with this running
    process."""
    access_token = _get_access_token()
    resp = httpx.get(
        f"{DRIVE_FILES_ENDPOINT}/{file_id}",
        headers={"Authorization": f"Bearer {access_token}"},
        params={"alt": "media"},
        timeout=120,
    )
    resp.raise_for_status()

    if RESTORE_STAGING_DIR.exists():
        shutil.rmtree(RESTORE_STAGING_DIR)
    RESTORE_STAGING_DIR.mkdir(parents=True)
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        zf.extractall(RESTORE_STAGING_DIR)

    PENDING_RESTORE_MARKER.write_text(json.dumps({"file_id": file_id, "staged_at": time.time()}), encoding="utf-8")


def apply_pending_restore_if_any() -> None:
    """Called first thing at backend startup, before migrations/DB access. Swaps in a staged
    restore left by `stage_restore`, if any."""
    if not PENDING_RESTORE_MARKER.exists():
        return
    try:
        db_path = get_database_path()
        staged_db = RESTORE_STAGING_DIR / db_path.name
        if staged_db.exists():
            if db_path.exists():
                backup_name = db_path.with_name(f"{db_path.stem}.pre-restore-{int(time.time())}{db_path.suffix}")
                shutil.move(str(db_path), str(backup_name))
            shutil.move(str(staged_db), str(db_path))

        staged_statements = RESTORE_STAGING_DIR / "statements"
        statements_dir = DATA_DIR / "statements"
        if staged_statements.exists():
            if statements_dir.exists():
                shutil.rmtree(statements_dir)
            shutil.move(str(staged_statements), str(statements_dir))
    finally:
        shutil.rmtree(RESTORE_STAGING_DIR, ignore_errors=True)
        PENDING_RESTORE_MARKER.unlink(missing_ok=True)
