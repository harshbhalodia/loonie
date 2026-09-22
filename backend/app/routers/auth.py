from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import User
from app.schemas import LoginRequest, TokenResponse, UserOut, UserSettingsIn
from app.security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.query(User).filter(func.lower(User.email) == payload.email.lower()).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    return TokenResponse(access_token=create_access_token(user.id))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> User:
    return user


@router.put("/me/settings", response_model=UserOut)
def update_settings(payload: UserSettingsIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> User:
    user.fiscal_year_start_month = payload.fiscal_year_start_month
    db.commit()
    db.refresh(user)
    return user
