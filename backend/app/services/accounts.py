"""Account lifecycle: registering accounts and making sure each has its own data folder."""
from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy.orm import Session

from app.database import user_session
from app.models import User
from app.registry import Account, find_account_by_email
from app.security import hash_password
from app.services.defaults import seed_default_category_groups

log = logging.getLogger("loonie.accounts")


class EmailTakenError(Exception):
    pass


def provision_user_data(account: Account) -> None:
    """Creates (or refreshes) the account's own database + its profile row. New accounts also get
    the default category groups. Safe to call on every sign-in."""
    db = user_session(account.id)
    try:
        user = db.get(User, account.id)
        if user is None:
            db.add(User(id=account.id, email=account.email, password_hash=account.password_hash, created_at=account.created_at))
            db.commit()
            seed_default_category_groups(db, account.id)
            log.info("provisioned data folder for new account %s", account.id)
        elif user.email != account.email or user.password_hash != account.password_hash:
            user.email = account.email
            user.password_hash = account.password_hash
            db.commit()
    finally:
        db.close()


def create_account(registry_db: Session, email: str, password: str) -> Account:
    email = email.strip().lower()
    if find_account_by_email(registry_db, email):
        raise EmailTakenError(email)
    account = Account(email=email, password_hash=hash_password(password))
    registry_db.add(account)
    registry_db.commit()
    registry_db.refresh(account)
    provision_user_data(account)
    return account


def touch_login(registry_db: Session, account: Account) -> None:
    account.last_login_at = datetime.utcnow()
    registry_db.commit()
