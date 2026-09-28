from fastapi import APIRouter, Depends, HTTPException

from app.config import get_google_drive_config
from app.deps import get_current_user
from app.models import User
from app.services import google_drive

router = APIRouter(prefix="/backup/google", tags=["backup"])


@router.get("/status")
def get_status(user: User = Depends(get_current_user)):
    return google_drive.get_status()


@router.post("/connect")
def connect(user: User = Depends(get_current_user)):
    try:
        google_drive.start_connect()
    except google_drive.GoogleDriveError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "connecting"}


@router.post("/disconnect")
def disconnect(user: User = Depends(get_current_user)):
    google_drive.disconnect()
    return {"status": "disconnected"}


@router.post("/backup-now")
def backup_now(user: User = Depends(get_current_user)):
    try:
        return google_drive.create_backup()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/backups")
def list_backups(user: User = Depends(get_current_user)):
    try:
        return {"backups": google_drive.list_backups()}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/restore/{file_id}")
def restore(file_id: str, user: User = Depends(get_current_user)):
    try:
        google_drive.stage_restore(file_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "restart_required"}


# No auth, loopback-only: the desktop shell (src-tauri) calls this right before it exits so a
# backup is taken even if the window is closed without ever opening Settings. Silently no-ops
# unless the user has already enabled + connected Google Drive.
@router.post("/shutdown-backup")
def shutdown_backup():
    if not get_google_drive_config().get("enabled", False) or not google_drive.is_connected():
        return {"status": "skipped"}
    try:
        google_drive.create_backup()
        return {"status": "ok"}
    except Exception:
        return {"status": "skipped"}
