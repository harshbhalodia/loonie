from fastapi import APIRouter, Depends

from app.config import get_ai_config
from app.deps import get_current_user
from app.models import User

router = APIRouter(prefix="/ai", tags=["ai"])


@router.get("/status")
def ai_status(user: User = Depends(get_current_user)):
    cfg = get_ai_config()
    return {
        "enabled": bool(cfg.get("enabled", False)),
        "provider": cfg.get("provider"),
        "model": cfg.get("model"),
        "style": cfg.get("style"),
        "endpoint": cfg.get("endpoint"),
    }
