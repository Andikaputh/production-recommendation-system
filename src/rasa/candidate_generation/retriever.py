"""Stage A: candidate generation.

Candidates are retrieved by mission category, availability, minimum rating,
and price limits. Diagnostics explain why products were excluded.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from rasa.missions.validation import Mission


@dataclass
class CandidateResult:
    candidates: pd.DataFrame
    diagnostics: dict = field(default_factory=dict)

    @property
    def empty(self) -> bool:
        return len(self.candidates) == 0


def retrieve_candidates(
    catalog: pd.DataFrame,
    mission: Mission,
    search_text: str | None = None,
    limit_per_category: int | None = None,
) -> CandidateResult:
    mission_categories = mission.all_categories
    preferences = mission.preferences

    scoped = catalog[catalog["category_id"].isin(mission_categories)].copy()
    diagnostics: dict = {
        "mission_categories": mission_categories,
        "total_products_in_scope": int(len(scoped)),
        "per_category": {},
        "excluded": {
            "unavailable": 0,
            "unknown_availability": 0,
            "below_min_rating": 0,
            "above_budget": 0,
            "above_max_item_price": 0,
            "text_search": 0,
        },
    }

    available_mask = scoped["availability_status"] == "available"
    diagnostics["excluded"]["unavailable"] = int((scoped["availability_status"] == "unavailable").sum())
    diagnostics["excluded"]["unknown_availability"] = int((scoped["availability_status"] == "unknown").sum())
    scoped = scoped[available_mask]

    if preferences.minimum_rating is not None:
        before = len(scoped)
        scoped = scoped[scoped["rating"] >= preferences.minimum_rating]
        diagnostics["excluded"]["below_min_rating"] = int(before - len(scoped))

    before = len(scoped)
    scoped = scoped[scoped["price"] <= mission.max_budget]
    diagnostics["excluded"]["above_budget"] = int(before - len(scoped))

    if preferences.max_item_price is not None:
        before = len(scoped)
        scoped = scoped[scoped["price"] <= preferences.max_item_price]
        diagnostics["excluded"]["above_max_item_price"] = int(before - len(scoped))

    if search_text:
        query = search_text.strip().lower()
        if query:
            haystack = (
                scoped["product_name"].str.lower() + " " + scoped["description"].str.lower() + " "
                + scoped["brand"].str.lower() + " " + scoped["category_name"].str.lower() + " "
                + scoped["subcategory"].str.lower()
            )
            before = len(scoped)
            scoped = scoped[haystack.str.contains(query, regex=False, na=False)]
            diagnostics["excluded"]["text_search"] = int(before - len(scoped))

    scoped = scoped.sort_values(["category_id", "rating", "review_count"], ascending=[True, False, False])
    if limit_per_category:
        scoped = scoped.groupby("category_id", group_keys=False).head(int(limit_per_category))

    for category_id in mission_categories:
        subset = scoped[scoped["category_id"] == category_id]
        diagnostics["per_category"][category_id] = {
            "candidates": int(len(subset)),
            "required": category_id in mission.required_categories,
            "min_price": float(subset["price"].min()) if len(subset) else None,
            "max_price": float(subset["price"].max()) if len(subset) else None,
            "merchants": int(subset["merchant_id"].nunique()) if len(subset) else 0,
        }

    diagnostics["empty_required_categories"] = [
        category_id for category_id in mission.required_categories
        if diagnostics["per_category"].get(category_id, {}).get("candidates", 0) == 0
    ]
    diagnostics["n_candidates"] = int(len(scoped))
    return CandidateResult(candidates=scoped.reset_index(drop=True), diagnostics=diagnostics)
