from datetime import datetime, timedelta, timezone

import bcrypt
from jose import JWTError, jwt

from app.config import get_auth_config

ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))


def create_access_token(subject: str) -> str:
    cfg = get_auth_config()
    expire_minutes = int(cfg.get("access_token_expire_minutes", 43200))
    expire = datetime.now(timezone.utc) + timedelta(minutes=expire_minutes)
    payload = {"sub": subject, "exp": expire}
    return jwt.encode(payload, cfg.get("jwt_secret", "insecure-dev-secret"), algorithm=ALGORITHM)


def decode_access_token(token: str) -> str | None:
    cfg = get_auth_config()
    try:
        payload = jwt.decode(token, cfg.get("jwt_secret", "insecure-dev-secret"), algorithms=[ALGORITHM])
    except JWTError:
        return None
    return payload.get("sub")
