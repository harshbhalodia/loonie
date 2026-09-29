import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_auth_config, get_cors_origins
from app.database import get_user_engine
from app.registry import Account, RegistrySession, account_count
from app.routers import (
    accounts,
    agents,
    ai,
    analytics,
    assets,
    assumptions,
    auth,
    backup,
    budgets,
    categories,
    category_groups,
    category_rules,
    cloud,
    decisions,
    entries,
    goals,
    jobs,
    keyword_candidates,
    marketplace,
    reminders,
    scenarios,
    settings,
    statements,
    topics,
    watchlist,
)
from app.services import accounts as account_service
from app.services import cloud_sync
from app.services.drive_restore import apply_pending_restore_if_any
from app.services.job_queue import start_worker
from app.services.legacy_migration import migrate_legacy_database_if_needed

log = logging.getLogger("loonie")


def _configure_logging() -> None:
    """Timestamped app log lines on stderr (captured to backend.log by the desktop shell)."""
    logger = logging.getLogger("loonie")
    if logger.handlers:
        return
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False


def _bootstrap_admin() -> None:
    """Optional headless bootstrap: creates the first account from config on an empty install."""
    with RegistrySession() as registry:
        if account_count(registry) > 0:
            return
        cfg = get_auth_config()
        email = cfg.get("initial_admin_email")
        password = cfg.get("initial_admin_password")
        if not email or not password:
            return
        account_service.create_account(registry, email, password)


def _open_all_accounts() -> None:
    """Migrates every account's database at startup so the first sign-in is instant."""
    with RegistrySession() as registry:
        user_ids = [a.id for a in registry.query(Account).all()]
    for user_id in user_ids:
        try:
            get_user_engine(user_id)
        except Exception:  # noqa: BLE001 - one broken account must not stop the app
            log.exception("could not open data for account %s", user_id)


@asynccontextmanager
async def lifespan(app: FastAPI):
    _configure_logging()
    log.info("Loonie backend starting")
    apply_pending_restore_if_any()
    migrate_legacy_database_if_needed()
    _bootstrap_admin()
    _open_all_accounts()
    start_worker()
    cloud_sync.start_worker()
    log.info("Loonie backend ready")
    yield
    cloud_sync.stop_worker()
    log.info("Loonie backend stopping")


app = FastAPI(title="Loonie API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(accounts.router)
app.include_router(assets.router)
app.include_router(categories.router)
app.include_router(category_groups.router)
app.include_router(category_rules.router)
app.include_router(entries.router)
app.include_router(budgets.router)
app.include_router(goals.router)
app.include_router(assumptions.router)
app.include_router(scenarios.router)
app.include_router(watchlist.router)
app.include_router(topics.router)
app.include_router(analytics.router)
app.include_router(agents.router)
app.include_router(agents.insights_router)
app.include_router(ai.router)
app.include_router(statements.router)
app.include_router(keyword_candidates.router)
app.include_router(reminders.router)
app.include_router(jobs.router)
app.include_router(decisions.router)
app.include_router(decisions.jev_router)
app.include_router(backup.router)
app.include_router(marketplace.router)
app.include_router(settings.router)
app.include_router(cloud.router)

@app.get("/health")
def health():
    return {"status": "ok"}
