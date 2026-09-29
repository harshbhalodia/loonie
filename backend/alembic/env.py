from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.config import get_database_path
from app.database import Base
from app import models  # noqa: F401  ensures all models are registered on Base.metadata

config = context.config
if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name)

# Programmatic callers (per-account migrations) set the URL themselves; the CLI falls back to the legacy database.
if not config.get_main_option("sqlalchemy.url"):
    config.set_main_option("sqlalchemy.url", f"sqlite:///{get_database_path()}")

target_metadata = Base.metadata


def include_object(obj, name, type_, reflected, compare_to):
    # Sync bookkeeping tables are created at runtime (services/sync_engine.py), not by Alembic.
    return not (type_ == "table" and name.startswith("sync_"))



def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True, render_as_batch=True, include_object=include_object)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(config.get_section(config.config_ini_section, {}), prefix="sqlalchemy.", poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True, include_object=include_object)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
