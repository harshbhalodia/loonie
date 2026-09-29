import logging

from fastapi import APIRouter, Depends, HTTPException

from app.config import get_google_drive_config
from app.deps import get_current_user
from app.models import User
from app.registry import Account, RegistrySession
from app.services import google_drive

log = logging.getLogger("loonie.backup")

router = APIRouter(prefix="/backup/google", tags=["backup"])


@router.get("/status")
def get_status(user: User = Depends(get_current_user)):
    return google_drive.get_status(user.id)


@router.post("/connect")
def connect(user: User = Depends(get_current_user)):
    try:
        google_drive.start_connect(user.id)
    except google_drive.GoogleDriveError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "connecting"}


@router.post("/disconnect")
def disconnect(user: User = Depends(get_current_user)):
    google_drive.disconnect(user.id)
    return {"status": "disconnected"}


@router.post("/backup-now")
def backup_now(user: User = Depends(get_current_user)):
    try:
        return google_drive.create_backup(user.id)
    except Exception as exc:
        log.warning("manual backup failed: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/backups")
def list_backups(user: User = Depends(get_current_user)):
    try:
        return {"backups": google_drive.list_backups(user.id)}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/restore/{file_id}")
def restore(file_id: str, user: User = Depends(get_current_user)):
    try:
        google_drive.stage_restore(user.id, file_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "restart_required"}


# No auth, loopback-only: the desktop shell (src-tauri) calls this right before it exits so a
# backup is taken even if the window is closed without ever opening Settings. Backs up every
# account that has already enabled + connected Google Drive; silently skips the rest.
@router.post("/shutdown-backup")
def shutdown_backup():
    if not get_google_drive_config().get("enabled", False):
        return {"status": "skipped"}
    with RegistrySession() as registry:
        user_ids = [a.id for a in registry.query(Account).all()]
    backed_up = 0
    for user_id in user_ids:
        if not google_drive.is_connected(user_id):
            continue
        try:
            google_drive.create_backup(user_id)
            backed_up += 1
        except Exception as exc:  # noqa: BLE001 - shutdown must never fail
            log.warning("shutdown backup failed for account %s: %s", user_id, exc)
    return {"status": "ok" if backed_up else "skipped"}
