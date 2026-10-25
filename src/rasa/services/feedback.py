"""Ingesti feedback anonim dan profiling sesi untuk rekomendasi berikutnya."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from rasa.config import settings
from rasa.db.models import InteractionEvent, Product
from rasa.services.missions import ensure_session
from rasa.utils import utcnow

FEEDBACK_EVENT_TYPES = ("impression", "click", "save", "add_to_list", "purchase_proxy", "dismiss")
POSITIVE_TYPES = ("click", "save", "add_to_list", "purchase_proxy")


class FeedbackValidationError(ValueError):
    pass


def _weight_map() -> dict[str, float]:
    return {key: float(value) for key, value in settings.get("features.event_weights", {}).items()}


def submit_feedback(
    session: Session,
    *,
    session_id: str,
    product_id: str | None,
    event_type: str,
    user_id: str | None = None,
    experiment_variant: str | None = None,
    source: str = "demo_ui",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if event_type not in FEEDBACK_EVENT_TYPES:
        raise FeedbackValidationError(
            f"event_type '{event_type}' tidak valid. Pilihan: {', '.join(FEEDBACK_EVENT_TYPES)}."
        )
    if not product_id:
        raise FeedbackValidationError("product_id wajib untuk setiap event feedback.")
    if product_id and session.get(Product, product_id) is None:
        raise FeedbackValidationError(f"Produk '{product_id}' tidak ditemukan pada katalog.")

    ensure_session(session, session_id, experiment_variant=experiment_variant)
    event = InteractionEvent(
        event_id=f"evt_{uuid.uuid4().hex[:16]}",
        session_id=session_id,
        user_id=user_id,
        product_id=product_id,
        event_type=event_type,
        event_timestamp=utcnow(),
        experiment_variant=experiment_variant,
        source=source,
        event_metadata=metadata or {},
    )
    session.add(event)
    session.flush()
    return {
        "event_id": event.event_id,
        "status": "recorded",
        "session_id": session_id,
        "event_type": event_type,
        "product_id": product_id,
        "timestamp": event.event_timestamp.isoformat(timespec="seconds"),
        "privacy": "Session ID anonim; tidak ada identitas pribadi yang disimpan.",
    }


def session_weights(session: Session, session_id: str, limit: int = 40) -> dict[str, float]:
    """Bobot interaksi positif terbaru dalam sesi (untuk session-based CF)."""
    if not session_id:
        return {}
    rows = list(
        session.scalars(
            select(InteractionEvent)
            .where(
                InteractionEvent.session_id == session_id,
                InteractionEvent.event_type.in_(POSITIVE_TYPES),
            )
            .order_by(InteractionEvent.event_timestamp.desc())
            .limit(limit)
        )
    )
    weights = _weight_map()
    result: dict[str, float] = {}
    for row in reversed(rows):
        if not row.product_id:
            continue
        result[row.product_id] = result.get(row.product_id, 0.0) + float(
            weights.get(row.event_type, 1.0) or 1.0
        )
    return result


def session_summary(session: Session, session_id: str, limit: int = 100) -> dict[str, Any]:
    rows = list(
        session.scalars(
            select(InteractionEvent)
            .where(InteractionEvent.session_id == session_id)
            .order_by(InteractionEvent.event_timestamp.desc())
            .limit(limit)
        )
    )
    counts: dict[str, int] = {}
    for row in rows:
        counts[row.event_type] = counts.get(row.event_type, 0) + 1
    return {
        "session_id": session_id,
        "total_events": len(rows),
        "counts_by_type": counts,
        "events": [
            {
                "event_id": row.event_id,
                "product_id": row.product_id,
                "event_type": row.event_type,
                "timestamp": row.event_timestamp.isoformat(timespec="seconds"),
                "source": row.source,
            }
            for row in rows
        ],
        "privacy": "Data sesi anonim; tidak memuat identitas pribadi.",
    }
