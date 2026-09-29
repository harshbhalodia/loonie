"""Runs Alembic migrations against any one SQLite file (each account has its own database)."""
from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config

from app.config import BACKEND_DIR


def upgrade_database(db_path: Path) -> None:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    # '%' is configparser's interpolation character, so it must be doubled inside the URL.
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}".replace("%", "%%"))
    # Don't let alembic reset the process-wide logging config (it would mute uvicorn/app logs).
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "head")
