"""Account lifecycle: registering accounts and making sure each has its own data folder."""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from app.database import user_session
from app.models import User
from app.registry import Account, find_account_by_email
from app.security import hash_password
from app.services.defaults import seed_default_category_groups

log = logging.getLogger("loonie.accounts")


class EmailTakenError(Exception):
    pass


def _adopt_foreign_owner(db: Session, account: Account) -> None:
    """Repairs a database that holds another owner's data (e.g. a backup made by a different
    install that was restored into this account by an older version): the rows are re-labelled to
    this account so they show up. Only acts when the previous owner is unambiguous."""
    foreign = db.execute(text("SELECT id, email FROM users WHERE id != :uid"), {"uid": account.id}).all()
    if not foreign:
        return
    same_email = [f for f in foreign if (f.email or "").lower() == account.email.lower()]
    candidates = same_email or (foreign if len(foreign) == 1 else [])
    if not candidates:
        log.warning("account %s: database has other owners %s; leaving them untouched", account.id, [f.id for f in foreign])
        return
    old_id = candidates[0].id

    inspector = inspect(db.get_bind())
    db.execute(text("UPDATE sync_state SET applying = 1"))  # keep the relabelling out of the sync queue
    try:
        for table in inspector.get_table_names():
            if any(c["name"] == "user_id" for c in inspector.get_columns(table)):
                db.execute(text(f'UPDATE OR REPLACE "{table}" SET user_id = :new WHERE user_id = :old'), {"new": account.id, "old": old_id})
        if db.execute(text("SELECT 1 FROM users WHERE id = :uid"), {"uid": account.id}).first():
            db.execute(text("DELETE FROM users WHERE id = :old"), {"old": old_id})
        else:
            db.execute(text("UPDATE users SET id = :new WHERE id = :old"), {"new": account.id, "old": old_id})

        for row_id, stored in db.execute(
            text("SELECT id, stored_path FROM wealth_statement_imports WHERE stored_path IS NOT NULL")
        ).all():
            parts = Path(stored.replace("\\", "/")).parts
            rest = None
            if len(parts) >= 3 and parts[:2] == ("data", "statements") and parts[2] in (old_id, account.id):
                rest = parts[3:]
            elif len(parts) >= 4 and parts[:2] == ("data", "users") and parts[2] in (old_id, account.id) and parts[3] == "statements":
                rest = parts[4:]
            if rest is not None:
                db.execute(
                    text("UPDATE wealth_statement_imports SET stored_path = :p WHERE id = :id"),
                    {"p": str(Path("data", "users", account.id, "statements", *rest)), "id": row_id},
                )
        # The account's own freshly seeded default groups now duplicate the adopted ones.
        db.execute(
            text(
                "DELETE FROM wealth_category_groups WHERE user_id = :uid "
                "AND id NOT IN (SELECT group_id FROM wealth_categories WHERE group_id IS NOT NULL) "
                "AND EXISTS (SELECT 1 FROM wealth_category_groups o WHERE o.user_id = wealth_category_groups.user_id "
                "AND o.name = wealth_category_groups.name AND o.created_at < wealth_category_groups.created_at)"
            ),
            {"uid": account.id},
        )
        db.commit()
        log.info("account %s: adopted data that belonged to %s", account.id, old_id)
    except Exception:
        db.rollback()
        raise
    finally:
        db.execute(text("UPDATE sync_state SET applying = 0"))
        db.commit()


def provision_user_data(account: Account) -> None:
    """Creates (or refreshes) the account's own database + its profile row. New accounts also get
    the default category groups. Safe to call on every sign-in."""
    db = user_session(account.id)
    try:
        _adopt_foreign_owner(db, account)
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
