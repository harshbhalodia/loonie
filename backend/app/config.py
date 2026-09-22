"""Loads config/config.yaml (creating it from config.example.yaml on first run).

Never overwrites an existing config.yaml — upgrades must preserve user settings.
"""
from __future__ import annotations

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


def _ensure_config_file() -> Path:
    if not CONFIG_PATH.exists():
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(CONFIG_EXAMPLE_PATH, CONFIG_PATH)
        # Give every fresh install its own random JWT signing key instead of the shared
        # example placeholder, so installs never sign tokens with a publicly-known secret.
        text = CONFIG_PATH.read_text(encoding="utf-8")
        text = text.replace("change-me-to-a-long-random-string", secrets.token_hex(32))
        CONFIG_PATH.write_text(text, encoding="utf-8")
    return CONFIG_PATH


@lru_cache
def load_config() -> dict[str, Any]:
    path = _ensure_config_file()
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


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
