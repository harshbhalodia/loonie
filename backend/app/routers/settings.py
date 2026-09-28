"""In-app integration settings (AI model, Jev, Google Drive) — so users configure Loonie from the
Settings screen instead of hand-editing config files. Secrets (API keys, OAuth client secret)
are write-only: the API reports whether one is set, never its value."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.config import get_ai_config, get_google_drive_config, get_jev_config, save_app_settings
from app.deps import get_current_user
from app.models import User
from app.schemas import (
    AiSettingsIn,
    AiSettingsOut,
    AiTestOut,
    GoogleDriveSettingsIn,
    GoogleDriveSettingsOut,
    IntegrationSettingsOut,
    JevSettingsIn,
    JevSettingsOut,
)
from app.services import ai_provider

router = APIRouter(prefix="/settings", tags=["settings"])


def _ai_out() -> AiSettingsOut:
    cfg = get_ai_config()
    return AiSettingsOut(
        enabled=bool(cfg.get("enabled", False)),
        endpoint=cfg.get("endpoint"),
        model=cfg.get("model"),
        style=cfg.get("style", "simple"),
        temperature=cfg.get("temperature"),
        max_tokens=cfg.get("max_tokens"),
    )


def _jev_out() -> JevSettingsOut:
    cfg = get_jev_config()
    return JevSettingsOut(
        enabled=bool(cfg.get("enabled", False)),
        api_key_set=bool(cfg.get("api_key")),
        model=cfg.get("model"),
    )


def _google_drive_out() -> GoogleDriveSettingsOut:
    cfg = get_google_drive_config()
    return GoogleDriveSettingsOut(
        enabled=bool(cfg.get("enabled", False)),
        client_id=cfg.get("client_id") or "",
        client_secret_set=bool(cfg.get("client_secret")),
    )


@router.get("/integrations", response_model=IntegrationSettingsOut)
def get_integrations(user: User = Depends(get_current_user)):
    return IntegrationSettingsOut(ai=_ai_out(), jev=_jev_out(), google_drive=_google_drive_out())


@router.put("/ai", response_model=AiSettingsOut)
def update_ai(payload: AiSettingsIn, user: User = Depends(get_current_user)):
    save_app_settings("ai", payload.model_dump(exclude_unset=True))
    return _ai_out()


@router.post("/ai/test", response_model=AiTestOut)
def test_ai(user: User = Depends(get_current_user)):
    """Sends a tiny prompt to the configured model so the user can confirm the connection works
    before relying on any agent. Uses only a fixed ping text — never any of the user's data."""
    try:
        reply = ai_provider.generate(
            "You are a connection test. Reply with the single word OK.", "ping", timeout=180
        )
    except ai_provider.AIProviderError as exc:
        return AiTestOut(ok=False, message=str(exc))
    return AiTestOut(ok=True, message=f"Connected. Model replied: {reply.strip()[:120]}")


@router.put("/jev", response_model=JevSettingsOut)
def update_jev(payload: JevSettingsIn, user: User = Depends(get_current_user)):
    values: dict = {"enabled": payload.enabled, "model": payload.model}
    if payload.api_key:
        values["api_key"] = payload.api_key.strip()
    save_app_settings("jev", values)
    return _jev_out()


@router.put("/google-drive", response_model=GoogleDriveSettingsOut)
def update_google_drive(payload: GoogleDriveSettingsIn, user: User = Depends(get_current_user)):
    values: dict = {"enabled": payload.enabled, "client_id": payload.client_id.strip()}
    if payload.client_secret:
        values["client_secret"] = payload.client_secret.strip()
    save_app_settings("google_drive", values)
    return _google_drive_out()
