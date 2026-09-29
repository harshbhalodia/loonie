import threading
from collections.abc import Generator

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import user_db_path
from app.security import decode_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


class Base(DeclarativeBase):
    pass


# One SQLite database per account: an account's data can never be reached through another
# account's session, and each folder can be backed up / synced on its own.
_engines: dict[str, Engine] = {}
_sessionmakers: dict[str, sessionmaker] = {}
_lock = threading.RLock()


def get_user_engine(user_id: str) -> Engine:
    """Returns the account's engine, creating + migrating its database on first use."""
    with _lock:
        engine = _engines.get(user_id)
        if engine is not None:
            return engine

        # Imported here because alembic/env.py imports this module for `Base`.
        from app.migrations import upgrade_database
        from app.services import sync_engine

        path = user_db_path(user_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        upgrade_database(path)

        engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
        sync_engine.install(engine)
        _engines[user_id] = engine
        _sessionmakers[user_id] = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        return engine


def user_session(user_id: str) -> Session:
    get_user_engine(user_id)
    return _sessionmakers[user_id]()


def dispose_user_engine(user_id: str) -> None:
    with _lock:
        engine = _engines.pop(user_id, None)
        _sessionmakers.pop(user_id, None)
    if engine is not None:
        engine.dispose()


def get_db(token: str | None = Depends(oauth2_scheme)) -> Generator[Session, None, None]:
    """Session on the signed-in account's own database (resolved from the bearer token)."""
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    user_id = decode_access_token(token) if token else None
    if not user_id:
        raise unauthorized
    try:
        if user_id not in _engines and not user_db_path(user_id).exists():
            raise unauthorized
        db = user_session(user_id)
    except ValueError:
        raise unauthorized from None
    try:
        yield db
    finally:
        db.close()
