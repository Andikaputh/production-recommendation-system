"""Stage E: explanation generation grounded in actual model signals and constraints."""

from __future__ import annotations

from typing import Any

from rasa.missions.validation import Mission, Preferences
from rasa.utils import format_idr


def _reason(code: str, label: str, detail: str, strength: float = 0.5) -> dict[str, Any]:
    return {
        "code": code,
        "label": label,
        "detail": detail,
        "strength": round(float(max(0.0, min(1.0, strength))), 3),
    }


def build_item_reasons(
    row: dict[str, Any],
    components: dict[str, float],
    mission: Mission,
    preferences: Preferences,
    flags: dict[str, Any],
    allocation: dict[str, float] | None = None,
) -> list[dict[str, Any]]:
    reasons: list[dict[str, Any]] = []
    category_id = row.get("category_id", "")
    category_name = row.get("category_name", category_id)
    price = float(row.get("price", 0))
    rating = float(row.get("rating", 0))
    target_budget = (allocation or {}).get(category_id, mission.max_budget)

    if category_id in mission.required_categories:
        reasons.append(_reason(
            "required_category",
            f"Required category {category_name}",
            f"This product satisfies the required {category_name} category in your mission.",
            1.0,
        ))
    elif category_id in mission.optional_categories:
        reasons.append(_reason(
            "optional_category",
            f"Optional category {category_name}",
            f"This product belongs to the optional {category_name} category.",
            0.6,
        ))

    if components.get("content", 0.0) >= 0.45:
        reasons.append(_reason(
            "content_match",
            "Description matches the goal",
            f"Content similarity is {components['content']:.2f} against the mission goal and selected attributes.",
            components["content"],
        ))

    matched_attributes: list[str] = []
    if preferences.style and row.get("style") in preferences.style:
        matched_attributes.append(f"style {row.get('style')}")
    if preferences.colors and row.get("color") in preferences.colors:
        matched_attributes.append(f"color {row.get('color')}")
    if preferences.brands and row.get("brand") in preferences.brands:
        matched_attributes.append(f"brand {row.get('brand')}")
    if matched_attributes:
        reasons.append(_reason(
            "preference_match",
            "Preference match",
            "Matches your preferences: " + ", ".join(matched_attributes) + ".",
            0.8,
        ))

    if preferences.minimum_rating is not None:
        reasons.append(_reason(
            "rating_threshold",
            "Rating threshold satisfied",
            f"The {rating:.1f} rating satisfies the minimum of {preferences.minimum_rating:.1f}.",
            0.7,
        ))
    elif rating >= 4.5:
        reasons.append(_reason(
            "high_rating",
            "High rating",
            f"The {rating:.1f} rating is high within the simulated catalog.",
            0.6,
        ))

    if price <= target_budget:
        reasons.append(_reason(
            "price_fit",
            "Price fits the allocation",
            f"{format_idr(price)} is within the category allocation of {format_idr(target_budget)}.",
            0.65,
        ))
    else:
        reasons.append(_reason(
            "price_tradeoff",
            "Price trade-off",
            f"{format_idr(price)} exceeds the soft category allocation of {format_idr(target_budget)}, "
            "but remains within the total budget.",
            0.4,
        ))

    if (
        (flags.get("user_known") or flags.get("session_personalized"))
        and components.get("affinity", 0.0) >= 0.35
    ):
        reasons.append(_reason(
            "history_affinity",
            "Behavioral match",
            "The brand, subcategory, style, or color resembles products you previously engaged with.",
            components["affinity"],
        ))

    if flags.get("user_known") and components.get("collaborative", 0.0) >= 0.35:
        reasons.append(_reason(
            "personalization",
            "Interaction-history match",
            "The collaborative score indicates similarity to products you previously engaged with.",
            components["collaborative"],
        ))
    if flags.get("session_personalized") and components.get("collaborative", 0.0) >= 0.25:
        reasons.append(_reason(
            "session_personalization",
            "Session feedback applied",
            "The recommendation accounts for products you recently rated in this session.",
            components["collaborative"],
        ))

    if flags.get("low_history_item"):
        reasons.append(_reason(
            "controlled_exposure",
            "Controlled exploration",
            "This low-history product passes quality and relevance thresholds and receives limited exposure.",
            0.35,
        ))
    if flags.get("cold_start_item"):
        reasons.append(_reason(
            "cold_start_item",
            "New product",
            "This product has no interaction history, so its score uses metadata, content, and quality.",
            0.3,
        ))

    reasons.sort(key=lambda item: item["strength"], reverse=True)
    return reasons[:5]


def build_basket_explanations(
    basket: dict[str, Any],
    mission: Mission,
    diagnostics: dict[str, Any],
) -> list[dict[str, Any]]:
    explanations: list[dict[str, Any]] = []
    items = basket.get("items", [])
    if not items:
        return explanations

    if basket.get("feasible"):
        explanations.append(_reason(
            "budget_ok",
            "Budget satisfied",
            f"Total {format_idr(basket['total_price'])} from a budget of "
            f"{format_idr(mission.max_budget)}; {format_idr(basket['budget_remaining'])} remains.",
            1.0,
        ))
        coverage = float(basket.get("required_category_coverage", 0.0))
        explanations.append(_reason(
            "coverage",
            "Required categories satisfied",
            f"{coverage * 100:.0f}% of required categories are covered.",
            coverage,
        ))
        explanations.append(_reason(
            "merchants",
            "Merchant count controlled",
            f"The basket uses {basket['merchant_count']} merchants "
            f"against a limit of {mission.max_merchants}.",
            0.8 if basket["merchant_count"] <= mission.max_merchants else 0.2,
        ))
        if diagnostics.get("objective_value") is not None:
            explanations.append(_reason(
                "optimizer",
                "Optimized combination",
                "This combination has the highest mission value among candidates that satisfy every hard constraint.",
                0.9,
            ))
        if diagnostics.get("solver") == "greedy_fallback":
            explanations.append(_reason(
                "solver_fallback",
                "Heuristic mode",
                "The ILP optimizer timed out, so a greedy heuristic built a basket that still satisfies every hard constraint.",
                0.5,
            ))
    else:
        explanations.append(_reason(
            "infeasible",
            "No combination satisfies every constraint",
            "The system never removes hard constraints silently. Review the relaxation suggestions.",
            1.0,
        ))
    return explanations


def build_tradeoffs(
    basket: dict[str, Any],
    alternative: dict[str, Any] | None,
) -> list[str]:
    if not alternative:
        return []
    tradeoffs: list[str] = []
    basket_total = float(basket.get("total_price", 0))
    alt_total = float(alternative.get("total_price", 0))
    if alt_total > basket_total:
        tradeoffs.append(
            f"The alternative costs {format_idr(alt_total - basket_total)} more and has a different aggregate relevance score."
        )
    elif alt_total < basket_total:
        tradeoffs.append(
            f"The alternative costs {format_idr(basket_total - alt_total)} less, potentially with lower quality or preference fit."
        )
    if alternative.get("merchant_count", 0) != basket.get("merchant_count", 0):
        tradeoffs.append(
            f"Merchant count differs: {basket.get('merchant_count')} vs. "
            f"{alternative.get('merchant_count')}."
        )
    if alternative.get("required_category_coverage", 1.0) < basket.get("required_category_coverage", 1.0):
        tradeoffs.append("The alternative does not cover every required category.")
    return tradeoffs
