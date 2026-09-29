"""Loads config/config.yaml (creating it from config.example.yaml on first run), then layers the
user's in-app settings (backend/data/app_settings.json, edited from the Settings screen) on top.

Never overwrites an existing config.yaml — upgrades must preserve user settings.
"""
from __future__ import annotations

import json
import re
import secrets
import shutil
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = REPO_ROOT / "config"
CONFIG_PATH = CONFIG_DIR / "config.yaml"
CONFIG_EXAMPLE_PATH = CONFIG_DIR / "config.example.yaml"
BACKEND_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BACKEND_DIR / "data"
APP_SETTINGS_PATH = DATA_DIR / "app_settings.json"
REGISTRY_PATH = DATA_DIR / "registry.db"
USERS_DIR = DATA_DIR / "users"

_USER_ID_RE = re.compile(r"^[A-Za-z0-9-]{8,64}$")


def user_dir(user_id: str) -> Path:
    """Each account keeps its own database, statements and integration tokens in one folder, so a
    single user's data can be backed up, synced or removed without touching anyone else's."""
    if not _USER_ID_RE.match(user_id):
        raise ValueError("Invalid user id")
    return USERS_DIR / user_id


def user_db_path(user_id: str) -> Path:
    return user_dir(user_id) / "lifeos.db"

# Only these sections/keys can ever be changed from the UI — everything else (auth secrets,
# database path, CORS) stays file-only so the Settings screen can't break the install.
EDITABLE_SETTINGS: dict[str, set[str]] = {
    "ai": {"enabled", "endpoint", "model", "style", "response_field", "temperature", "max_tokens"},
    "jev": {"enabled", "api_key", "model", "base_url"},
    "google_drive": {"enabled", "client_id", "client_secret"},
    "cloud": {"base_url"},
}


def _ensure_config_file() -> Path:
    if not CONFIG_PATH.exists():
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(CONFIG_EXAMPLE_PATH, CONFIG_PATH)
        # Give every fresh install its own random JWT signing key instead of the shared
        # example placeholder, so installs never sign tokens with a publicly-known secret.
        text = CONFIG_PATH.read_text(encoding="utf-8")
        text = text.replace("change-me-to-a-long-random-string", secrets.token_hex(32))
        text = text.replace("change-me-marketplace-secret", secrets.token_hex(16))
        CONFIG_PATH.write_text(text, encoding="utf-8")
    return CONFIG_PATH


def _read_app_settings() -> dict[str, dict[str, Any]]:
    if not APP_SETTINGS_PATH.exists():
        return {}
    try:
        raw = json.loads(APP_SETTINGS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return raw if isinstance(raw, dict) else {}


@lru_cache
def load_config() -> dict[str, Any]:
    path = _ensure_config_file()
    with path.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}

    for section, values in _read_app_settings().items():
        allowed = EDITABLE_SETTINGS.get(section)
        if not allowed or not isinstance(values, dict):
            continue
        merged = dict(cfg.get(section) or {})
        merged.update({k: v for k, v in values.items() if k in allowed})
        cfg[section] = merged
    return cfg


def save_app_settings(section: str, values: dict[str, Any]) -> None:
    """Persists UI-edited settings for one section and reloads config immediately (no restart).
    Unknown sections/keys are ignored so the UI can never write arbitrary config."""
    allowed = EDITABLE_SETTINGS.get(section)
    if not allowed:
        raise ValueError(f"Section {section!r} is not editable from the app")

    settings = _read_app_settings()
    current = dict(settings.get(section) or {})
    current.update({k: v for k, v in values.items() if k in allowed})
    settings[section] = current

    APP_SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    APP_SETTINGS_PATH.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    load_config.cache_clear()


def get_database_path() -> Path:
    cfg = load_config()
    raw_path = cfg.get("database", {}).get("path", "./data/lifeos.db")
    path = Path(raw_path)
    if not path.is_absolute():
        path = (BACKEND_DIR / path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def get_cors_origins() -> list[str]:
    cfg = load_config()
    return cfg.get("app", {}).get("cors_origins", ["http://localhost:5173"])


def get_auth_config() -> dict[str, Any]:
    cfg = load_config()
    return cfg.get("auth", {})


def get_ai_config() -> dict[str, Any]:
    cfg = load_config()
    return cfg.get("ai", {})


def get_jev_config() -> dict[str, Any]:
    cfg = load_config()
    return cfg.get("jev", {})


def get_google_drive_config() -> dict[str, Any]:
    cfg = load_config()
    return cfg.get("google_drive", {})


def get_marketplace_config() -> dict[str, Any]:
    cfg = load_config()
    return cfg.get("marketplace", {})


def get_cloud_config() -> dict[str, Any]:
    cfg = load_config()
    return cfg.get("cloud", {})
