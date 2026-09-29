"""Device-level account registry: which accounts exist on this installation and their login
credentials. It holds NO financial data — each account's data lives in its own folder
(`backend/data/users/<id>/`), so accounts stay fully separate from each other."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, create_engine, func
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from app.config import REGISTRY_PATH


class RegistryBase(DeclarativeBase):
    pass


class Account(RegistryBase):
    __tablename__ = "accounts"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    email: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
_engine = create_engine(f"sqlite:///{REGISTRY_PATH}", connect_args={"check_same_thread": False})
RegistrySession = sessionmaker(autocommit=False, autoflush=False, bind=_engine)
RegistryBase.metadata.create_all(_engine)


def get_registry_db():
    db = RegistrySession()
    try:
        yield db
    finally:
        db.close()


def find_account_by_email(db: Session, email: str) -> Account | None:
    return db.query(Account).filter(func.lower(Account.email) == email.lower()).first()


def account_count(db: Session) -> int:
    return db.query(Account).count()
