"""Shopping-mission validation and constraint-conflict detection."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from rasa.config import settings


@dataclass
class Preferences:
    style: list[str] = field(default_factory=list)
    colors: list[str] = field(default_factory=list)
    brands: list[str] = field(default_factory=list)
    minimum_rating: float | None = None
    max_item_price: float | None = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> Preferences:
        payload = payload or {}
        return cls(
            style=[str(item) for item in payload.get("style", []) or []],
            colors=[str(item) for item in payload.get("colors", []) or []],
            brands=[str(item) for item in payload.get("brands", []) or []],
            minimum_rating=(
                float(payload["minimum_rating"]) if payload.get("minimum_rating") is not None else None
            ),
            max_item_price=(
                float(payload["max_item_price"]) if payload.get("max_item_price") is not None else None
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "style": self.style,
            "colors": self.colors,
            "brands": self.brands,
            "minimum_rating": self.minimum_rating,
            "max_item_price": self.max_item_price,
        }


@dataclass
class Mission:
    goal: str
    required_categories: list[str]
    optional_categories: list[str]
    max_budget: float
    max_merchants: int
    preferences: Preferences = field(default_factory=Preferences)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> Mission:
        return cls(
            goal=str(payload.get("goal", "")).strip(),
            required_categories=[str(item) for item in payload.get("required_categories", []) or []],
            optional_categories=[str(item) for item in payload.get("optional_categories", []) or []],
            max_budget=float(payload.get("max_budget", 0) or 0),
            max_merchants=int(payload.get("max_merchants", 1) or 1),
            preferences=Preferences.from_dict(payload.get("preferences")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "goal": self.goal,
            "required_categories": self.required_categories,
            "optional_categories": self.optional_categories,
            "max_budget": self.max_budget,
            "max_merchants": self.max_merchants,
            "preferences": self.preferences.to_dict(),
        }

    @property
    def all_categories(self) -> list[str]:
        return list(dict.fromkeys([*self.required_categories, *self.optional_categories]))


@dataclass
class ValidationIssue:
    code: str
    message: str
    field: str | None = None
    severity: str = "error"


@dataclass
class ValidationResult:
    valid: bool
    errors: list[ValidationIssue]
    warnings: list[ValidationIssue]
    normalized: Mission | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "errors": [issue.__dict__ for issue in self.errors],
            "warnings": [issue.__dict__ for issue in self.warnings],
            "normalized": self.normalized.to_dict() if self.normalized else None,
        }


def budget_allocation(mission: Mission, catalog: pd.DataFrame) -> dict[str, float]:
    """Allocate budget by category using median catalog prices.

    The allocation is a soft price-fit feature; total budget remains a hard
    optimizer constraint.
    """
    medians: dict[str, float] = {}
    for category_id in mission.all_categories:
        subset = catalog[catalog["category_id"] == category_id]
        medians[category_id] = float(subset["price"].median()) if len(subset) else 0.0
    required = mission.required_categories
    optional = mission.optional_categories
    weights: dict[str, float] = {}
    for category_id in required:
        weights[category_id] = medians.get(category_id, 0.0) or 1.0
    for category_id in optional:
        # Optional categories receive less weight so they do not crowd out required categories.
        weights[category_id] = (medians.get(category_id, 0.0) or 1.0) * 0.5
    total = sum(weights.values())
    if total <= 0:
        equal = mission.max_budget / max(1, len(mission.all_categories))
        return {category_id: equal for category_id in mission.all_categories}
    return {
        category_id: mission.max_budget * (weight / total) for category_id, weight in weights.items()
    }


def minimum_budget(mission: Mission, catalog: pd.DataFrame) -> float:
    available = catalog[catalog["availability_status"] == "available"]
    total = 0.0
    for category_id in mission.required_categories:
        subset = available[available["category_id"] == category_id]
        if len(subset) == 0:
            return float("inf")
        total += float(subset["price"].min())
    return total


def minimum_merchants(mission: Mission, catalog: pd.DataFrame) -> int:
    """Estimate the minimum merchant count using a simple set-cover heuristic."""
    available = catalog[catalog["availability_status"] == "available"]
    chosen_merchants: set[str] = set()
    for category_id in mission.required_categories:
        subset = available[available["category_id"] == category_id]
        if len(subset) == 0:
            return 10**6
        # Select the merchant that appears most frequently in this category.
        merchant = subset["merchant_id"].value_counts().idxmax()
        chosen_merchants.add(str(merchant))
    return max(1, len(chosen_merchants))


def validate_mission(mission: Mission, catalog: pd.DataFrame, categories: pd.DataFrame) -> ValidationResult:
    errors: list[ValidationIssue] = []
    warnings: list[ValidationIssue] = []
    known_categories = set(categories["category_id"])
    rating_min = float(catalog["rating"].min())
    rating_max = float(catalog["rating"].max())

    if not mission.goal:
        errors.append(ValidationIssue("goal_required", "A mission goal is required.", "goal"))
    if len(mission.goal) > 500:
        errors.append(ValidationIssue(
            "goal_too_long", "The mission goal is limited to 500 characters.", "goal"
        ))

    if not mission.required_categories:
        errors.append(ValidationIssue(
            "required_categories_required",
            "Select at least one required category.",
            "required_categories",
        ))
    unknown_required = [item for item in mission.required_categories if item not in known_categories]
    unknown_optional = [item for item in mission.optional_categories if item not in known_categories]
    if unknown_required or unknown_optional:
        errors.append(ValidationIssue(
            "unknown_category",
            f"Unknown categories: {sorted(set(unknown_required + unknown_optional))}.",
            "required_categories",
        ))

    duplicates = len(mission.required_categories) != len(set(mission.required_categories))
    if duplicates:
        errors.append(ValidationIssue(
            "duplicate_category", "Required categories must be unique.", "required_categories"
        ))
    overlap = set(mission.required_categories) & set(mission.optional_categories)
    if overlap:
        errors.append(ValidationIssue(
            "category_overlap",
            f"A category cannot be both required and optional: {sorted(overlap)}.",
            "optional_categories",
        ))

    if mission.max_budget <= 0:
        errors.append(ValidationIssue(
            "invalid_budget", "The budget must be a positive number.", "max_budget"
        ))
    elif mission.max_budget < 1000:
        warnings.append(ValidationIssue(
            "very_low_budget",
            "A budget below IDR 1,000 is unlikely to satisfy the mission.",
            "max_budget",
            "warning",
        ))

    if mission.max_merchants < 1:
        errors.append(ValidationIssue(
            "invalid_max_merchants",
            "The merchant limit must be a positive integer.",
            "max_merchants",
        ))
    elif mission.max_merchants > 10:
        warnings.append(ValidationIssue(
            "high_merchant_limit",
            "A merchant limit above 10 is rarely needed for a shopping mission.",
            "max_merchants",
            "warning",
        ))

    if mission.preferences.minimum_rating is not None:
        if mission.preferences.minimum_rating < rating_min or mission.preferences.minimum_rating > rating_max:
            errors.append(ValidationIssue(
                "rating_out_of_scale",
                f"The minimum rating must be within the dataset range {rating_min:.1f}-{rating_max:.1f}.",
                "preferences.minimum_rating",
            ))
    if mission.preferences.max_item_price is not None and mission.preferences.max_item_price <= 0:
        errors.append(ValidationIssue(
            "invalid_max_item_price",
            "The maximum price per product must be positive.",
            "preferences.max_item_price",
        ))

    # Detect conflicts that make a valid form infeasible.
    if not errors and mission.required_categories:
        cheapest = minimum_budget(mission, catalog)
        if cheapest > mission.max_budget:
            warnings.append(ValidationIssue(
                "budget_conflict",
                f"The budget of IDR {mission.max_budget:,.0f} is below the cheapest total "
                f"of IDR {cheapest:,.0f} for all required categories.",
                "max_budget",
                "warning",
            ))
        min_merchants = minimum_merchants(mission, catalog)
        if mission.max_merchants < min_merchants:
            warnings.append(ValidationIssue(
                "merchant_conflict",
                f"Required categories are estimated to need at least {min_merchants} merchants, "
                f"but the current limit is {mission.max_merchants}.",
                "max_merchants",
                "warning",
            ))
        available = catalog[catalog["availability_status"] == "available"]
        empty_categories = [
            category_id for category_id in mission.required_categories
            if len(available[available["category_id"] == category_id]) == 0
        ]
        if empty_categories:
            warnings.append(ValidationIssue(
                "empty_category",
                f"Categories with no available products: {empty_categories}.",
                "required_categories",
                "warning",
            ))

    normalized = Mission(
        goal=mission.goal.strip(),
        required_categories=list(dict.fromkeys(mission.required_categories)),
        optional_categories=[item for item in dict.fromkeys(mission.optional_categories)
                             if item not in mission.required_categories],
        max_budget=float(mission.max_budget),
        max_merchants=int(mission.max_merchants),
        preferences=mission.preferences,
    )
    return ValidationResult(valid=len(errors) == 0, errors=errors, warnings=warnings, normalized=normalized)


def rating_scale(catalog: pd.DataFrame) -> tuple[float, float]:
    return float(catalog["rating"].min()), float(catalog["rating"].max())


def default_max_merchants() -> int:
    return 2


def max_budget_ceiling() -> float:
    return float(settings.get("api.max_budget_ceiling", 50_000_000))
