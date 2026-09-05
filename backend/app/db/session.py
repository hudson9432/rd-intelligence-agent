"""SQLAlchemy engine, session factory, and FastAPI dependency."""

import sqlite3
from collections.abc import Generator
from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.db.base import Base


def _enable_sqlite_foreign_keys(
    dbapi_connection: sqlite3.Connection, connection_record: object
) -> None:
    """Enable SQLite foreign-key cascades for every new connection."""

    del connection_record
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def create_database_engine(
    database_url: str,
    *,
    echo: bool = False,
    in_memory: bool = False,
) -> Engine:
    """Create an engine with SQLite-safe defaults."""

    kwargs: dict[str, object] = {"echo": echo}
    if database_url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
        if in_memory:
            kwargs["poolclass"] = StaticPool

    database_engine = create_engine(database_url, **kwargs)
    if database_url.startswith("sqlite"):
        event.listen(database_engine, "connect", _enable_sqlite_foreign_keys)
    return database_engine


def create_session_factory(database_engine: Engine) -> sessionmaker[Session]:
    """Create a typed session factory for an engine."""

    return sessionmaker(
        bind=database_engine,
        class_=Session,
        autoflush=False,
        expire_on_commit=False,
    )


settings = get_settings()
engine = create_database_engine(settings.database_url, echo=settings.database_echo)
SessionLocal = create_session_factory(engine)


def _ensure_sqlite_directory(database_url: str) -> None:
    prefix = "sqlite:///"
    if not database_url.startswith(prefix) or database_url.endswith(":memory:"):
        return
    database_path = Path(database_url.removeprefix(prefix))
    database_path.parent.mkdir(parents=True, exist_ok=True)


def init_db(database_engine: Engine = engine) -> None:
    """Create MVP tables after importing the complete model registry."""

    from app import models  # noqa: F401

    if database_engine is engine:
        _ensure_sqlite_directory(settings.database_url)
    Base.metadata.create_all(bind=database_engine)


def get_db() -> Generator[Session]:
    """Yield one request-scoped SQLAlchemy session."""

    with SessionLocal() as session:
        yield session
