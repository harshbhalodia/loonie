from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.config import get_auth_config
from app.database import get_db
from app.deps import get_current_user
from app.models import User
from app.registry import account_count, find_account_by_email, get_registry_db
from app.schemas import LoginRequest, SetupRequest, SetupStatusOut, TokenResponse, UserOut, UserSettingsIn
from app.security import create_access_token, verify_password
from app.services import accounts as account_service

router = APIRouter(prefix="/auth", tags=["auth"])


def _registration_allowed() -> bool:
    return bool(get_auth_config().get("allow_registration", True))


@router.get("/setup-status", response_model=SetupStatusOut)
def setup_status(registry_db: Session = Depends(get_registry_db)) -> SetupStatusOut:
    count = account_count(registry_db)
    return SetupStatusOut(needs_setup=count == 0, account_count=count, allow_registration=_registration_allowed())


@router.post("/register", response_model=TokenResponse)
def register(payload: SetupRequest, registry_db: Session = Depends(get_registry_db)) -> TokenResponse:
    """Creates a new account with its own separate data folder. Open to anyone using this install
    (e.g. family members on one PC) unless `auth.allow_registration` is switched off."""
    if account_count(registry_db) > 0 and not _registration_allowed():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Creating new accounts is turned off.")
    try:
        account = account_service.create_account(registry_db, payload.email, payload.password)
    except account_service.EmailTakenError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="An account with this email already exists. Please sign in."
        ) from None
    account_service.touch_login(registry_db, account)
    return TokenResponse(access_token=create_access_token(account.id))


@router.post("/setup", response_model=TokenResponse)
def first_run_setup(payload: SetupRequest, registry_db: Session = Depends(get_registry_db)) -> TokenResponse:
    """Kept for older clients — identical to `/register`."""
    return register(payload, registry_db)


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, registry_db: Session = Depends(get_registry_db)) -> TokenResponse:
    account = find_account_by_email(registry_db, payload.email)
    if not account or not verify_password(payload.password, account.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    account_service.provision_user_data(account)
    account_service.touch_login(registry_db, account)
    return TokenResponse(access_token=create_access_token(account.id))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> User:
    return user


@router.put("/me/settings", response_model=UserOut)
def update_settings(payload: UserSettingsIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> User:
    user.fiscal_year_start_month = payload.fiscal_year_start_month
    db.commit()
    db.refresh(user)
    return user
