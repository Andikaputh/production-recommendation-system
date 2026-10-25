"""Skema database relasional RASA (SQLAlchemy 2.0).

Skema kompatibel dengan SQLite (default demo) dan PostgreSQL (produksi).
Event log bersifat append-oriented; data agregat dashboard dihitung dari event
dan tabel rekomendasi, bukan disimpan sebagai satu baris mutable.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from rasa.utils import utcnow


class Base(DeclarativeBase):
    pass


class Category(Base):
    __tablename__ = "categories"

    category_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    category_name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    subcategories: Mapped[list | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class Merchant(Base):
    __tablename__ = "merchants"

    merchant_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    merchant_name: Mapped[str] = mapped_column(String(160), nullable=False)
    city: Mapped[str | None] = mapped_column(String(80))
    rating: Mapped[float] = mapped_column(Float, nullable=False, default=4.3)
    is_low_history: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class Product(Base):
    __tablename__ = "products"

    product_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    product_name: Mapped[str] = mapped_column(String(220), nullable=False)
    category_id: Mapped[str] = mapped_column(ForeignKey("categories.category_id"), nullable=False, index=True)
    subcategory: Mapped[str | None] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(Text, nullable=False)
    brand: Mapped[str] = mapped_column(String(100), nullable=False)
    price: Mapped[float] = mapped_column(Numeric(12, 2, asdecimal=False), nullable=False)
    rating: Mapped[float] = mapped_column(Float, nullable=False)
    review_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    availability_status: Mapped[str] = mapped_column(String(20), nullable=False, default="unknown")
    merchant_id: Mapped[str] = mapped_column(ForeignKey("merchants.merchant_id"), nullable=False, index=True)
    attributes: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    __table_args__ = (
        Index("ix_products_category_availability", "category_id", "availability_status"),
        Index("ix_products_price", "price"),
    )


class ProductAttribute(Base):
    __tablename__ = "product_attributes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.product_id"), nullable=False, index=True)
    attribute_key: Mapped[str] = mapped_column(String(80), nullable=False)
    attribute_value: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (UniqueConstraint("product_id", "attribute_key", name="uq_product_attribute"),)


class AnonymousSession(Base):
    __tablename__ = "anonymous_sessions"

    session_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    experiment_variant: Mapped[str | None] = mapped_column(String(80))
    user_agent_family: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class UserPreference(Base):
    __tablename__ = "user_preferences"

    user_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    preferred_categories: Mapped[list | None] = mapped_column(JSON)
    preferred_price_range: Mapped[dict | None] = mapped_column(JSON)
    preferred_brands: Mapped[list | None] = mapped_column(JSON)
    preferred_styles: Mapped[list | None] = mapped_column(JSON)
    preferred_colors: Mapped[list | None] = mapped_column(JSON)
    price_sensitivity: Mapped[str | None] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class ShoppingMission(Base):
    __tablename__ = "shopping_missions"

    mission_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("anonymous_sessions.session_id"), nullable=False, index=True)
    goal_text: Mapped[str] = mapped_column(Text, nullable=False)
    max_budget: Mapped[float] = mapped_column(Numeric(14, 2, asdecimal=False), nullable=False)
    max_merchants: Mapped[int] = mapped_column(Integer, nullable=False)
    preferences: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(30), default="validated", nullable=False)
    validation_warnings: Mapped[list | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class MissionRequiredCategory(Base):
    __tablename__ = "mission_required_categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    mission_id: Mapped[str] = mapped_column(ForeignKey("shopping_missions.mission_id"), nullable=False, index=True)
    category_id: Mapped[str] = mapped_column(ForeignKey("categories.category_id"), nullable=False)

    __table_args__ = (UniqueConstraint("mission_id", "category_id", name="uq_mission_required_category"),)


class MissionOptionalCategory(Base):
    __tablename__ = "mission_optional_categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    mission_id: Mapped[str] = mapped_column(ForeignKey("shopping_missions.mission_id"), nullable=False, index=True)
    category_id: Mapped[str] = mapped_column(ForeignKey("categories.category_id"), nullable=False)

    __table_args__ = (UniqueConstraint("mission_id", "category_id", name="uq_mission_optional_category"),)


class InteractionEvent(Base):
    __tablename__ = "interaction_events"

    event_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    user_id: Mapped[str | None] = mapped_column(String(80), index=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.product_id"), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    event_timestamp: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False, index=True)
    experiment_variant: Mapped[str | None] = mapped_column(String(80))
    source: Mapped[str | None] = mapped_column(String(80))
    event_metadata: Mapped[dict | None] = mapped_column("metadata", JSON)

    __table_args__ = (
        Index("ix_events_session_type", "session_id", "event_type"),
        Index("ix_events_timestamp_type", "event_timestamp", "event_type"),
    )


class RecommendationRequest(Base):
    __tablename__ = "recommendation_requests"

    request_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    mission_id: Mapped[str | None] = mapped_column(ForeignKey("shopping_missions.mission_id"), index=True)
    session_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    model_version: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    strategy: Mapped[str] = mapped_column(String(60), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    latency_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    candidate_count: Mapped[int] = mapped_column(Integer, default=0)
    fallback_used: Mapped[bool] = mapped_column(Boolean, default=False)
    request_payload: Mapped[dict | None] = mapped_column(JSON)
    response_snapshot: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False, index=True)


class RecommendationItem(Base):
    __tablename__ = "recommendation_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(
        ForeignKey("recommendation_requests.request_id"), nullable=False, index=True
    )
    product_id: Mapped[str] = mapped_column(ForeignKey("products.product_id"), nullable=False, index=True)
    rank_position: Mapped[int] = mapped_column(Integer, nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    component_scores: Mapped[dict | None] = mapped_column(JSON)
    explanation: Mapped[dict | None] = mapped_column(JSON)
    selected_in_basket: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class BasketSolution(Base):
    __tablename__ = "basket_solutions"

    basket_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    request_id: Mapped[str | None] = mapped_column(
        ForeignKey("recommendation_requests.request_id"), index=True
    )
    mission_id: Mapped[str | None] = mapped_column(ForeignKey("shopping_missions.mission_id"), index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    total_price: Mapped[float] = mapped_column(Numeric(14, 2, asdecimal=False), nullable=False, default=0)
    budget_remaining: Mapped[float] = mapped_column(Numeric(14, 2, asdecimal=False), nullable=False, default=0)
    merchant_count: Mapped[int] = mapped_column(Integer, default=0)
    required_category_coverage: Mapped[float] = mapped_column(Float, default=0.0)
    solver: Mapped[str] = mapped_column(String(60), default="none")
    explanation: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False, index=True)


class BasketItem(Base):
    __tablename__ = "basket_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    basket_id: Mapped[str] = mapped_column(ForeignKey("basket_solutions.basket_id"), nullable=False, index=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.product_id"), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    unit_price: Mapped[float] = mapped_column(Numeric(12, 2, asdecimal=False), nullable=False)
    role: Mapped[str] = mapped_column(String(30), default="required", nullable=False)


class ExperimentDefinition(Base):
    __tablename__ = "experiment_definitions"

    experiment_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(String(120))
    config: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class ExperimentAssignment(Base):
    __tablename__ = "experiment_assignments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    experiment_id: Mapped[str] = mapped_column(ForeignKey("experiment_definitions.experiment_id"), nullable=False)
    variant: Mapped[str] = mapped_column(String(60), nullable=False)
    assigned_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    __table_args__ = (UniqueConstraint("session_id", "experiment_id", name="uq_experiment_assignment"),)


class ModelVersion(Base):
    __tablename__ = "model_versions"

    model_version: Mapped[str] = mapped_column(String(80), primary_key=True)
    trained_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    dataset_version: Mapped[str | None] = mapped_column(String(80))
    config_hash: Mapped[str | None] = mapped_column(String(80))
    metrics: Mapped[dict | None] = mapped_column(JSON)
    artifact_path: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


__all__ = [
    "Base",
    "Category",
    "Merchant",
    "Product",
    "ProductAttribute",
    "AnonymousSession",
    "UserPreference",
    "ShoppingMission",
    "MissionRequiredCategory",
    "MissionOptionalCategory",
    "InteractionEvent",
    "RecommendationRequest",
    "RecommendationItem",
    "BasketSolution",
    "BasketItem",
    "ExperimentDefinition",
    "ExperimentAssignment",
    "ModelVersion",
]
