"""Persistence for shopping missions and anonymous sessions."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from rasa.db.models import (
    AnonymousSession,
    MissionOptionalCategory,
    MissionRequiredCategory,
    ShoppingMission,
)
from rasa.missions.validation import Mission, Preferences
from rasa.utils import utcnow


def ensure_session(session: Session, session_id: str, experiment_variant: str | None = None) -> AnonymousSession:
    existing = session.get(AnonymousSession, session_id)
    if existing is not None:
        existing.last_seen_at = utcnow()
        if experiment_variant and not existing.experiment_variant:
            existing.experiment_variant = experiment_variant
        return existing
    new_session = AnonymousSession(
        session_id=session_id,
        experiment_variant=experiment_variant,
        created_at=utcnow(),
        last_seen_at=utcnow(),
    )
    session.add(new_session)
    session.flush()
    return new_session


def create_mission(
    session: Session,
    mission: Mission,
    *,
    session_id: str,
    warnings: list[dict[str, Any]] | None = None,
    status: str = "validated",
) -> ShoppingMission:
    ensure_session(session, session_id)
    mission_id = f"msn_{uuid.uuid4().hex[:12]}"
    record = ShoppingMission(
        mission_id=mission_id,
        session_id=session_id,
        goal_text=mission.goal,
        max_budget=mission.max_budget,
        max_merchants=mission.max_merchants,
        preferences=mission.preferences.to_dict(),
        status=status,
        validation_warnings=warnings or [],
        created_at=utcnow(),
    )
    session.add(record)
    # Model intentionally keeps a flat schema without ORM relationships. Flush
    # the parent explicitly so SQLite/PostgreSQL foreign keys are satisfied
    # before association rows are inserted.
    session.flush()
    for category_id in mission.required_categories:
        session.add(MissionRequiredCategory(mission_id=mission_id, category_id=category_id))
    for category_id in mission.optional_categories:
        session.add(MissionOptionalCategory(mission_id=mission_id, category_id=category_id))
    session.flush()
    return record


def mission_to_payload(session: Session, mission_id: str) -> dict[str, Any] | None:
    record = session.get(ShoppingMission, mission_id)
    if record is None:
        return None
    required = [
        row.category_id
        for row in session.scalars(
            select(MissionRequiredCategory).where(MissionRequiredCategory.mission_id == mission_id)
        )
    ]
    optional = [
        row.category_id
        for row in session.scalars(
            select(MissionOptionalCategory).where(MissionOptionalCategory.mission_id == mission_id)
        )
    ]
    return {
        "mission_id": record.mission_id,
        "session_id": record.session_id,
        "goal": record.goal_text,
        "required_categories": required,
        "optional_categories": optional,
        "max_budget": float(record.max_budget),
        "max_merchants": int(record.max_merchants),
        "preferences": record.preferences or {},
        "status": record.status,
        "validation_warnings": record.validation_warnings or [],
        "created_at": record.created_at.isoformat(timespec="seconds") if record.created_at else None,
    }


def mission_from_record(session: Session, mission_id: str) -> Mission | None:
    payload = mission_to_payload(session, mission_id)
    if payload is None:
        return None
    return Mission(
        goal=payload["goal"],
        required_categories=payload["required_categories"],
        optional_categories=payload["optional_categories"],
        max_budget=payload["max_budget"],
        max_merchants=payload["max_merchants"],
        preferences=Preferences.from_dict(payload["preferences"]),
    )
