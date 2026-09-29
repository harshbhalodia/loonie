"""Link this account to Loonie Cloud so its data syncs automatically across devices."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field

from app.config import save_app_settings
from app.deps import get_current_user
from app.models import User
from app.services import cloud_sync

router = APIRouter(prefix="/cloud", tags=["cloud"])


class ConnectIn(BaseModel):
    mode: Literal["login", "register"] = "login"
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)
    # Only needed when both this device and the cloud workspace already hold data.
    strategy: Literal["merge", "replace"] | None = None


class ServerIn(BaseModel):
    base_url: str = Field(max_length=300)


@router.get("/status")
def get_status(user: User = Depends(get_current_user)):
    return cloud_sync.status(user.id)


@router.put("/server")
def set_server(payload: ServerIn, user: User = Depends(get_current_user)):
    if cloud_sync.load_state(user.id).get("token"):
        raise HTTPException(status_code=409, detail="Disconnect from Loonie Cloud before changing the server address.")
    try:
        url = cloud_sync.validate_base_url(payload.base_url.strip())
    except cloud_sync.CloudError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    save_app_settings("cloud", {"base_url": url})
    return cloud_sync.status(user.id)


@router.post("/connect")
def connect(payload: ConnectIn, user: User = Depends(get_current_user)):
    try:
        return cloud_sync.connect(user.id, payload.mode, payload.email, payload.password, payload.strategy)
    except cloud_sync.CloudError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/sync")
def sync(user: User = Depends(get_current_user)):
    try:
        cloud_sync.sync_now(user.id)
    except cloud_sync.CloudError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return cloud_sync.status(user.id)


@router.post("/disconnect")
def disconnect(user: User = Depends(get_current_user)):
    cloud_sync.disconnect(user.id)
    return cloud_sync.status(user.id)
