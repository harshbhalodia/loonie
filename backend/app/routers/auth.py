from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import User
from app.schemas import LoginRequest, SetupRequest, SetupStatusOut, TokenResponse, UserOut, UserSettingsIn
from app.security import create_access_token, hash_password, verify_password
from app.services.defaults import seed_default_category_groups

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/setup-status", response_model=SetupStatusOut)
def setup_status(db: Session = Depends(get_db)) -> SetupStatusOut:
    return SetupStatusOut(needs_setup=db.query(User).count() == 0)


@router.post("/setup", response_model=TokenResponse)
def first_run_setup(payload: SetupRequest, db: Session = Depends(get_db)) -> TokenResponse:
    """Creates the owner account on a brand-new install. Only ever works while zero users exist —
    once any account is created this permanently returns 409, so it can't be used to add users."""
    if db.query(User).count() > 0:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Loonie is already set up. Please sign in.")
    user = User(email=payload.email.lower(), password_hash=hash_password(payload.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    seed_default_category_groups(db, user.id)
    return TokenResponse(access_token=create_access_token(user.id))


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
