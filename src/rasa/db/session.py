"""Database engine, session factory, and initialization."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from rasa.config import settings
from rasa.db.models import Base

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def _connect_args(url: str) -> dict:
    if url.startswith("sqlite"):
        return {"check_same_thread": False}
    return {}


def get_engine(url: str | None = None, echo: bool = False) -> Engine:
    global _engine, _session_factory
    target_url = url or settings.database_url
    if _engine is not None and str(_engine.url) == target_url and not echo:
        return _engine
    _engine = create_engine(
        target_url,
        echo=echo,
        future=True,
        pool_pre_ping=True,
        connect_args=_connect_args(target_url),
    )
    if target_url.startswith("sqlite"):
        @event.listens_for(_engine, "connect")
        def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()
    _session_factory = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False, future=True)
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    global _session_factory
    if _session_factory is None:
        get_engine()
    assert _session_factory is not None
    return _session_factory


def reset_engine(url: str | None = None) -> Engine:
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None
    return get_engine(url)


@contextmanager
def session_scope() -> Iterator[Session]:
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db(url: str | None = None, drop: bool = False) -> Engine:
    engine = get_engine(url)
    if drop:
        Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    return engine


def healthcheck() -> tuple[bool, str | None]:
    try:
        engine = get_engine()
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True, None
    except Exception as exc:  # pragma: no cover - bergantung lingkungan
        return False, str(exc)
