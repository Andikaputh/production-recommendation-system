"""Skema request/response API RASA (Pydantic v2)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from rasa.config import settings
from rasa.missions.validation import Mission, Preferences

EventType = Literal["impression", "click", "save", "add_to_list", "purchase_proxy", "dismiss"]


class PreferencesIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    style: list[str] = Field(default_factory=list, max_length=5)
    colors: list[str] = Field(default_factory=list, max_length=10)
    brands: list[str] = Field(default_factory=list, max_length=10)
    minimum_rating: float | None = Field(default=None, ge=0, le=5)
    max_item_price: float | None = Field(default=None, gt=0)

    def to_domain(self) -> Preferences:
        return Preferences.from_dict(self.model_dump())


class MissionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal: str = Field(min_length=3, max_length=500)
    required_categories: list[str] = Field(min_length=1, max_length=6)
    optional_categories: list[str] = Field(default_factory=list, max_length=5)
    max_budget: float = Field(gt=0, le=settings.get("api.max_budget_ceiling", 50_000_000))
    max_merchants: int = Field(default=2, ge=1, le=settings.get("api.max_merchants_ceiling", 10))

    @field_validator("required_categories", "optional_categories")
    @classmethod
    def _dedupe(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(item.strip() for item in value if item.strip()))

    def to_domain(self, preferences: PreferencesIn | None = None) -> Mission:
        return Mission.from_dict({
            **self.model_dump(),
            "preferences": (preferences or PreferencesIn()).model_dump(),
        })


class ParseMissionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=3, max_length=2000)


class RecommendationContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(default="demo-session", min_length=3, max_length=80)
    user_id: str | None = Field(default=None, max_length=80)
    strategy: Literal[
        "popularity_global",
        "popularity_category",
        "content",
        "collaborative",
        "hybrid",
        "hybrid_mission",
        "hybrid_basket",
        "hybrid_exposure",
    ] = "hybrid_mission"
    top_k: int = Field(default=10, ge=1, le=settings.get("api.top_k_max", 20))
    include_comparison: bool = False
    experiment_id: str | None = Field(default=None, max_length=40)
    search_text: str | None = Field(default=None, max_length=120)


class RecommendationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mission: MissionIn
    preferences: PreferencesIn = Field(default_factory=PreferencesIn)
    context: RecommendationContext = Field(default_factory=RecommendationContext)


class BasketOptimizeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mission: MissionIn
    preferences: PreferencesIn = Field(default_factory=PreferencesIn)
    context: RecommendationContext = Field(default_factory=RecommendationContext)


class FeedbackIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(min_length=3, max_length=80)
    product_id: str = Field(min_length=1, max_length=50)
    event_type: EventType
    user_id: str | None = Field(default=None, max_length=80)
    experiment_variant: str | None = Field(default=None, max_length=40)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("metadata")
    @classmethod
    def _metadata_size(cls, value: dict[str, Any]) -> dict[str, Any]:
        if len(str(value)) > 2000:
            raise ValueError("metadata is limited to 2,000 characters")
        return value


class ErrorBody(BaseModel):
    code: str
    message: str
    details: dict[str, Any] | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody
    request_id: str | None = None
