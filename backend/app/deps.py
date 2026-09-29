from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.config import user_db_path
from app.database import get_db, oauth2_scheme
from app.models import User
from app.security import decode_access_token


def get_current_user_id(token: str | None = Depends(oauth2_scheme)) -> str:
    """Signed-in account id without opening its database (for operations that replace the file)."""
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    user_id = decode_access_token(token) if token else None
    if not user_id:
        raise credentials_error
    try:
        if not user_db_path(user_id).exists():
            raise credentials_error
    except ValueError:
        raise credentials_error from None
    return user_id



def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not token:
        raise credentials_error

    user_id = decode_access_token(token)
    if not user_id:
        raise credentials_error

    user = db.get(User, user_id)
    if not user:
        raise credentials_error

    return user
