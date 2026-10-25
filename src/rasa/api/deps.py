"""Dependency injection untuk API."""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy.orm import Session

from rasa.db.session import session_scope


def get_db() -> Iterator[Session]:
    with session_scope() as session:
        yield session
