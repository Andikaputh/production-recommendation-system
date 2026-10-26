"""Stages B through D: preference scoring, mission feasibility, and hybrid ranking."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from rasa.candidate_generation.retriever import retrieve_candidates
from rasa.config import settings
from rasa.explanations.generator import build_item_reasons
from rasa.features.builder import CollaborativeModel, ContentModel, PopularityModel
from rasa.missions.validation import Mission, Preferences, budget_allocation
from rasa.utils import clamp, format_idr

STRATEGIES = (
    "popularity_global",
    "popularity_category",
    "content",
    "collaborative",
    "hybrid",
    "hybrid_mission",
    "hybrid_basket",
    "hybrid_exposure",
)

STOPWORDS = {
    "the", "for", "and", "with", "from", "i", "want", "buy", "shopping",
    "maximum", "cost", "budget", "can", "or", "on", "is", "this", "that",
    "bundle", "needs", "must", "minimum", "merchant", "product", "item",
    "find", "search", "prepare", "essentials", "activity", "possible",
    "more", "budget-friendly", "new", "daily", "everyday",
}


@dataclass
class RankedItem:
    product_id: str
    product_name: str
    category_id: str
    category_name: str
    subcategory: str
    brand: str
    price: float
    rating: float
    review_count: int
    availability_status: str
    merchant_id: str
    merchant_name: str
    merchant_rating: float
    style: str
    color: str
    material: str
    score: float
    components: dict[str, float] = field(default_factory=dict)
    reasons: list[dict[str, Any]] = field(default_factory=list)
    flags: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "product_id": self.product_id,
            "product_name": self.product_name,
            "category_id": self.category_id,
            "category_name": self.category_name,
            "subcategory": self.subcategory,
            "brand": self.brand,
            "price": float(self.price),
            "rating": float(self.rating),
            "review_count": int(self.review_count),
            "availability_status": self.availability_status,
            "merchant_id": self.merchant_id,
            "merchant_name": self.merchant_name,
            "merchant_rating": float(self.merchant_rating),
            "style": self.style,
            "color": self.color,
            "material": self.material,
            "score": round(float(self.score), 6),
            "components": {key: round(float(value), 6) for key, value in self.components.items()},
            "reasons": self.reasons,
            "flags": self.flags,
        }


@dataclass
class RankResult:
    items: list[RankedItem]
    scored: pd.DataFrame
    diagnostics: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "items": [item.to_dict() for item in self.items],
            "diagnostics": self.diagnostics,
        }


def _align(scores: np.ndarray, model_ids: list[str], product_ids: list[str]) -> np.ndarray:
    mapping = {product_id: idx for idx, product_id in enumerate(model_ids)}
    output = np.zeros(len(product_ids), dtype=float)
    for idx, product_id in enumerate(product_ids):
        model_idx = mapping.get(product_id)
        if model_idx is not None:
            output[idx] = scores[model_idx]
    return output


def _component_normalize(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=float)
    if values.size == 0:
        return values
    low, high = float(np.min(values)), float(np.max(values))
    if high - low < 1e-12:
        return np.ones_like(values) if high > 0 else np.zeros_like(values)
    return (values - low) / (high - low)


def _goal_tokens(goal: str) -> set[str]:
    tokens = set(re.findall(r"[a-zA-Z]{4,}", goal.lower()))
    return {token for token in tokens if token not in STOPWORDS}


class HybridRanker:
    def __init__(
        self,
        content: ContentModel,
        collaborative: CollaborativeModel,
        popularity: PopularityModel,
        config: dict[str, Any] | None = None,
    ) -> None:
        self.content = content
        self.collaborative = collaborative
        self.popularity = popularity
        self.config = config or {
            "weights": settings.get("ranking.weights", {}),
            "top_k": settings.get("ranking.top_k", 10),
            "candidate_limit_per_category": settings.get("ranking.candidate_limit_per_category", 60),
            "min_interactions": settings.get("ranking.cold_start.min_interactions", 3),
            "exposure_alpha": settings.get("ranking.controlled_exposure.alpha", 0.08),
            "exposure_max_share": settings.get("ranking.controlled_exposure.max_share", 0.20),
            "low_history_quantile": settings.get("ranking.controlled_exposure.low_history_quantile", 0.40),
            "hybrid_baseline_collaborative": settings.get(
                "ranking.hybrid_baseline.collaborative", 0.25
            ),
            "hybrid_baseline_content": settings.get("ranking.hybrid_baseline.content", 0.55),
            "hybrid_baseline_quality": settings.get("ranking.hybrid_baseline.quality", 0.20),
        }
        self.weights = {key: float(value) for key, value in self.config.get("weights", {}).items()}
        counts = list(self.popularity.global_counts.values()) or [0]
        quantile = float(self.config.get("low_history_quantile", 0.4))
        self.low_history_threshold = max(1.0, float(np.quantile(counts, quantile)))

    # ------------------------------------------------------------------
    def _affinity_scores(
        self,
        candidates: pd.DataFrame,
        weights: dict[str, float] | None,
        catalog_lookup: dict[str, dict[str, str]],
    ) -> np.ndarray | None:
        """Match explicit attributes against history or session context, separate from latent CF."""
        if not weights:
            return None
        history = catalog_lookup
        brand_counts: dict[str, float] = {}
        style_counts: dict[str, float] = {}
        color_counts: dict[str, float] = {}
        subcategory_counts: dict[str, float] = {}
        total = 0.0
        for product_id, weight in weights.items():
            record = history.get(product_id)
            if record is None:
                continue
            weight = float(weight)
            brand_counts[str(record["brand"])] = brand_counts.get(str(record["brand"]), 0.0) + weight
            style_counts[str(record["style"])] = style_counts.get(str(record["style"]), 0.0) + weight
            color_counts[str(record["color"])] = color_counts.get(str(record["color"]), 0.0) + weight
            subcategory_counts[str(record["subcategory"])] = (
                subcategory_counts.get(str(record["subcategory"]), 0.0) + weight
            )
            total += weight
        if total <= 0:
            return None
        scores = []
        for row in candidates.itertuples():
            brand = brand_counts.get(str(row.brand), 0.0) / total
            style = style_counts.get(str(row.style), 0.0) / total
            color = color_counts.get(str(row.color), 0.0) / total
            subcategory = subcategory_counts.get(str(row.subcategory), 0.0) / total
            scores.append(0.42 * brand + 0.26 * subcategory + 0.20 * style + 0.12 * color)
        return np.asarray(scores, dtype=float)

    def _content_scores(
        self,
        candidates: pd.DataFrame,
        mission: Mission,
        history_weights: dict[str, float] | None,
        session_weights: dict[str, float] | None,
        catalog_lookup: dict[str, dict[str, str]],
    ) -> np.ndarray:
        preference_text = " ".join([
            mission.goal,
            " ".join(mission.preferences.style),
            " ".join(mission.preferences.colors),
            " ".join(mission.preferences.brands),
            " ".join(
                candidates.loc[candidates["category_id"] == category_id, "category_name"].iloc[0]
                for category_id in mission.all_categories
                if (candidates["category_id"] == category_id).any()
            ),
        ])
        text_scores = _align(
            self.content.text_scores(preference_text), self.content.item_ids, candidates["product_id"].tolist()
        )

        profile_weights = history_weights or {}
        if not profile_weights and session_weights:
            profile_weights = session_weights
        profile = self.content.profile_from_items(profile_weights) if profile_weights else None
        profile_scores = _align(
            self.content.scores_for_profile(profile),
            self.content.item_ids,
            candidates["product_id"].tolist(),
        )
        if profile is not None:
            return 0.6 * text_scores + 0.4 * profile_scores
        return text_scores

    def _collaborative_scores(
        self,
        candidates: pd.DataFrame,
        user_id: str | None,
        session_weights: dict[str, float] | None,
    ) -> tuple[np.ndarray, int]:
        n_interactions = self.collaborative.user_interaction_count(user_id)
        user_scores = self.collaborative.score_user(user_id)
        user_aligned = _align(user_scores, self.collaborative.item_ids, candidates["product_id"].tolist())
        session_scores = self.collaborative.score_session(session_weights)
        session_aligned = _align(session_scores, self.collaborative.item_ids, candidates["product_id"].tolist())
        if n_interactions > 0 and session_weights:
            combined = 0.7 * user_aligned + 0.3 * session_aligned
        elif n_interactions > 0:
            combined = user_aligned
        else:
            combined = session_aligned
        return _component_normalize(combined), n_interactions

    def _mission_scores(
        self,
        candidates: pd.DataFrame,
        mission: Mission,
        allocation: dict[str, float],
        cold_user: bool,
        popularity_category: np.ndarray,
    ) -> np.ndarray:
        preferences = mission.preferences
        goal_tokens = _goal_tokens(mission.goal)
        scores = []
        for row in candidates.itertuples():
            attributes_text = " ".join([
                str(row.product_name), str(row.description), str(row.category_name),
                str(row.subcategory), str(row.brand), str(row.style), str(row.color),
                " ".join(row.tags if isinstance(row.tags, (list, tuple)) else []),
            ]).lower()
            item_tokens = set(re.findall(r"[a-zA-Z]{4,}", attributes_text))
            goal_overlap = len(goal_tokens & item_tokens) / len(goal_tokens) if goal_tokens else 0.0

            category_score = 1.0 if row.category_id in mission.required_categories else 0.55
            rating_fit = clamp(
                (float(row.rating) - (preferences.minimum_rating or 3.5) + 0.25) / 0.9
                if preferences.minimum_rating is not None
                else (float(row.rating) - 3.5) / 1.5
            )
            target = allocation.get(str(row.category_id), mission.max_budget)
            price = float(row.price)
            price_fit = 1.0 if price <= target else clamp(1.0 - (price - target) / max(target, 1.0))
            budget_headroom = clamp((mission.max_budget - price) / max(mission.max_budget, 1.0))

            parts: list[tuple[float, float]] = [
                (0.26, category_score),
                (0.16, goal_overlap),
                (0.12, rating_fit),
                (0.16, price_fit),
                (0.05, budget_headroom),
            ]
            if preferences.style:
                parts.append((0.11, 1.0 if str(row.style) in preferences.style else 0.0))
            if preferences.colors:
                parts.append((0.07, 1.0 if str(row.color) in preferences.colors else 0.0))
            if preferences.brands:
                parts.append((0.08, 1.0 if str(row.brand) in preferences.brands else 0.0))
            if cold_user:
                # Cold-start fallback: popularity within relevant categories.
                parts.append((0.08, float(popularity_category[len(scores)])))
            total_weight = sum(weight for weight, _ in parts)
            scores.append(sum(weight * value for weight, value in parts) / total_weight if total_weight else 0.0)
        return np.asarray(scores, dtype=float)

    def _quality_scores(self, candidates: pd.DataFrame) -> np.ndarray:
        rating = ((candidates["rating"].to_numpy(dtype=float) - 3.5) / 1.5).clip(0, 1)
        review = np.log1p(candidates["review_count"].to_numpy(dtype=float)) / np.log1p(900)
        merchant = candidates.get("merchant_rating", pd.Series([4.3] * len(candidates))).to_numpy(dtype=float)
        merchant_norm = np.clip((merchant - 3.8) / 1.1, 0, 1)
        availability = (candidates["availability_status"] == "available").astype(float).to_numpy()
        return 0.45 * rating + 0.20 * np.clip(review, 0, 1) + 0.20 * merchant_norm + 0.15 * availability

    def _resolve_weights(self, strategy: str, n_interactions: int, has_session: bool) -> dict[str, float]:
        if strategy == "popularity_global":
            return {"popularity": 1.0}
        if strategy == "popularity_category":
            return {"popularity": 1.0}
        if strategy == "content":
            return {"content": 1.0}
        if strategy == "collaborative":
            return {"collaborative": 1.0}
        weights = dict(self.weights)
        if strategy == "hybrid":
            # The hybrid baseline without mission signals uses a fixed composition so
            # the EXP-005 versus EXP-006 comparison remains meaningful after tuning.
            weights = {
                "collaborative": float(self.config.get("hybrid_baseline_collaborative", 0.25)),
                "content": float(self.config.get("hybrid_baseline_content", 0.55)),
                "quality": float(self.config.get("hybrid_baseline_quality", 0.20)),
            }
        min_interactions = int(self.config.get("min_interactions", 3))
        if n_interactions == 0 and not has_session:
            weights["collaborative"] = 0.0
        elif n_interactions < min_interactions:
            weights["collaborative"] *= n_interactions / min_interactions
        total = sum(weights.values())
        if total <= 0:
            return {"content": 0.5, "mission": 0.5}
        return {key: value / total for key, value in weights.items()}

    # ------------------------------------------------------------------
    def rank(
        self,
        catalog: pd.DataFrame,
        mission: Mission,
        *,
        user_id: str | None = None,
        session_weights: dict[str, float] | None = None,
        history_weights: dict[str, float] | None = None,
        strategy: str = "hybrid_mission",
        top_k: int | None = None,
        search_text: str | None = None,
        exclude_product_ids: set[str] | None = None,
    ) -> RankResult:
        if strategy not in STRATEGIES:
            raise ValueError(f"Unknown strategy: {strategy}")
        top_k = int(top_k or self.config.get("top_k", 10))
        candidate_limit = self.config.get("candidate_limit_per_category")

        candidate_result = retrieve_candidates(
            catalog, mission, search_text=search_text, limit_per_category=candidate_limit
        )
        candidates = candidate_result.candidates
        if exclude_product_ids:
            before_exclusion = len(candidates)
            candidates = candidates[~candidates["product_id"].isin(exclude_product_ids)]
            candidate_result.diagnostics["excluded_already_seen"] = int(
                before_exclusion - len(candidates)
            )
        diagnostics: dict[str, Any] = {
            "strategy": strategy,
            "candidate_generation": candidate_result.diagnostics,
            "n_candidates": int(len(candidates)),
            "top_k": top_k,
            "cold_start": {},
            "exploration": {},
        }
        if candidates.empty:
            diagnostics["reason"] = "no_candidates"
            return RankResult(items=[], scored=pd.DataFrame(), diagnostics=diagnostics)

        product_ids = candidates["product_id"].tolist()
        allocation = budget_allocation(mission, catalog)
        catalog_lookup = {
            str(row["product_id"]): {
                "brand": str(row.get("brand", "")),
                "style": str(row.get("style", "")),
                "color": str(row.get("color", "")),
                "subcategory": str(row.get("subcategory", "")),
            }
            for row in candidates.to_dict("records")
        }
        # Lookup spans the full catalog because history may contain
        # products outside the current mission candidate set.
        catalog_lookup.update({
            str(row["product_id"]): {
                "brand": str(row.get("brand", "")),
                "style": str(row.get("style", "")),
                "color": str(row.get("color", "")),
                "subcategory": str(row.get("subcategory", "")),
            }
            for row in catalog.to_dict("records")
        })
        content_raw = self._content_scores(
            candidates, mission, history_weights, session_weights, catalog_lookup
        )
        profile_weights = history_weights or session_weights
        affinity_raw = self._affinity_scores(candidates, profile_weights, catalog_lookup)
        if affinity_raw is None:
            affinity_raw = np.zeros(len(candidates), dtype=float)
        cf_raw, n_interactions = self._collaborative_scores(candidates, user_id, session_weights)
        popularity_global = _align(
            self.popularity.global_scores(catalog), catalog["product_id"].tolist(), product_ids
        )
        popularity_category = _align(
            self.popularity.category_scores(catalog, mission.all_categories),
            catalog["product_id"].tolist(),
            product_ids,
        )
        min_interactions = int(self.config.get("min_interactions", 3))
        cold_user = n_interactions < min_interactions
        mission_raw = self._mission_scores(
            candidates, mission, allocation, cold_user, _component_normalize(popularity_category)
        )
        quality_raw = self._quality_scores(candidates)

        components = {
            "collaborative": _component_normalize(cf_raw),
            "content": _component_normalize(content_raw),
            "mission": _component_normalize(mission_raw),
            "quality": _component_normalize(quality_raw),
            "affinity": _component_normalize(affinity_raw),
            "popularity_global": _component_normalize(popularity_global),
            "popularity_category": _component_normalize(popularity_category),
        }
        weights = self._resolve_weights(strategy, n_interactions, bool(session_weights))
        if strategy in {"popularity_global", "popularity_category"}:
            weights = {"popularity": 1.0}
            popularity_key = "popularity_global" if strategy == "popularity_global" else "popularity_category"
            score = components[popularity_key]
        else:
            score = np.zeros(len(candidates), dtype=float)
            for key, weight in weights.items():
                score += weight * components.get(key, np.zeros(len(candidates)))

        # Stage C: feasibility flags after retrieval filters hard constraints.
        prices = candidates["price"].to_numpy(dtype=float)
        score = np.where(prices <= mission.max_budget, score, -np.inf)

        counts = candidates["product_id"].map(self.popularity.global_counts).fillna(0).to_numpy(dtype=float)
        low_history = counts <= self.low_history_threshold
        cold_item = counts == 0
        quality_floor = candidates["rating"].to_numpy(dtype=float) >= (
            (mission.preferences.minimum_rating or 3.5) - float(
                settings.get("ranking.controlled_exposure.quality_floor_rating_delta", 0.1)
            )
        )
        content_median = float(np.median(components["content"])) if len(components["content"]) else 0.0
        exploration_eligible = low_history & quality_floor & (components["content"] >= content_median * 0.8)

        exploration_count = 0
        if strategy == "hybrid_exposure":
            alpha = float(self.config.get("exposure_alpha", 0.08))
            bonus = np.where(exploration_eligible, alpha, 0.0)
            score = score + bonus
            max_share = float(self.config.get("exposure_max_share", 0.2))
            cap = max(1, int(round(max_share * top_k)))
            order = np.argsort(-score, kind="stable")
            kept: list[int] = []
            deferred: list[int] = []
            low_count = 0
            for idx in order:
                if exploration_eligible[idx]:
                    if low_count >= cap:
                        deferred.append(int(idx))
                        continue
                    low_count += 1
                kept.append(int(idx))
            order = np.asarray(kept + deferred, dtype=int)
            exploration_count = low_count
        else:
            order = np.argsort(-score, kind="stable")

        scored = candidates.copy()
        scored["candidate_order"] = np.arange(len(candidates))
        scored["score"] = score
        for name, values in components.items():
            scored[f"component_{name}"] = values
        scored["is_low_history"] = low_history
        scored["is_cold_start_item"] = cold_item
        scored["exploration_eligible"] = exploration_eligible
        scored = scored.sort_values(["score", "product_id"], ascending=[False, True]).reset_index(drop=True)

        user_known = n_interactions >= min_interactions
        diagnostics["cold_start"] = {
            "user_known": bool(self.collaborative.has_user(user_id)),
            "n_user_interactions": int(n_interactions),
            "is_cold_user": bool(cold_user),
            "session_personalized": bool(session_weights),
            "fallback": (
                "mission_preferences_and_content" if cold_user
                else "collaborative_plus_mission"
            ),
        }
        diagnostics["weights"] = {key: round(float(value), 4) for key, value in weights.items()}
        diagnostics["exploration"] = {
            "enabled": strategy == "hybrid_exposure",
            "eligible_items": int(exploration_eligible.sum()),
            "selected_low_history": int(exploration_count),
            "low_history_threshold": float(self.low_history_threshold),
        }
        diagnostics["allocation"] = {key: round(float(value), 2) for key, value in allocation.items()}

        items: list[RankedItem] = []
        for rank_position, row_idx in enumerate(order[:top_k], start=1):
            row = candidates.iloc[int(row_idx)]
            flags = {
                "user_known": user_known,
                "session_personalized": bool(session_weights),
                "low_history_item": bool(low_history[row_idx]),
                "cold_start_item": bool(cold_item[row_idx]),
                "exploration_selected": bool(
                    strategy == "hybrid_exposure" and exploration_eligible[row_idx]
                ),
                "rank": rank_position,
            }
            component_values = {
                "collaborative": float(components["collaborative"][row_idx]),
                "content": float(components["content"][row_idx]),
                "mission": float(components["mission"][row_idx]),
                "quality": float(components["quality"][row_idx]),
                "affinity": float(components["affinity"][row_idx]),
                "popularity": float(components["popularity_category"][row_idx]),
            }
            reasons = build_item_reasons(
                row.to_dict(), component_values, mission, mission.preferences, flags, allocation
            )
            items.append(
                RankedItem(
                    product_id=str(row["product_id"]),
                    product_name=str(row["product_name"]),
                    category_id=str(row["category_id"]),
                    category_name=str(row["category_name"]),
                    subcategory=str(row.get("subcategory", "")),
                    brand=str(row.get("brand", "")),
                    price=float(row["price"]),
                    rating=float(row["rating"]),
                    review_count=int(row["review_count"]),
                    availability_status=str(row["availability_status"]),
                    merchant_id=str(row["merchant_id"]),
                    merchant_name=str(row.get("merchant_name", row["merchant_id"])),
                    merchant_rating=float(row.get("merchant_rating", 0.0) or 0.0),
                    style=str(row.get("style", "")),
                    color=str(row.get("color", "")),
                    material=str(row.get("material", "")),
                    score=float(score[row_idx]),
                    components=component_values,
                    reasons=reasons,
                    flags=flags,
                )
            )

        diagnostics["score_range"] = {
            "min": float(np.min(score[np.isfinite(score)])) if np.isfinite(score).any() else None,
            "max": float(np.max(score[np.isfinite(score)])) if np.isfinite(score).any() else None,
        }
        diagnostics["required_category_availability"] = {
            category_id: int((candidates["category_id"] == category_id).sum())
            for category_id in mission.required_categories
        }
        return RankResult(items=items, scored=scored, diagnostics=diagnostics)


def simulate_mission_for_user(
    user_row: pd.Series,
    catalog: pd.DataFrame,
    max_budget: float | None = None,
    max_merchants: int = 2,
) -> Mission:
    """Build a synthetic mission from user preferences for offline evaluation."""
    import json

    preferred = user_row.get("preferred_categories", [])
    if isinstance(preferred, str):
        preferred = json.loads(preferred)
    required = [category for category in preferred if category in set(catalog["category_id"])][:4]
    if not required:
        required = ["stationery"]
    subset = catalog[catalog["category_id"].isin(required)]
    if max_budget is None:
        median = float(subset["price"].median()) * len(required)
        max_budget = max(120_000.0, median * 1.55)
    styles = user_row.get("preferred_styles", [])
    if isinstance(styles, str):
        styles = json.loads(styles)
    brands = user_row.get("preferred_brands", [])
    if isinstance(brands, str):
        brands = json.loads(brands)
    colors = user_row.get("preferred_colors", [])
    if isinstance(colors, str):
        colors = json.loads(colors)
    return Mission(
        goal=f"Prepare {', '.join(required)} for everyday needs",
        required_categories=required,
        optional_categories=[],
        max_budget=float(max_budget),
        max_merchants=max_merchants,
        preferences=Preferences(
            style=list(styles),
            colors=list(colors),
            brands=list(brands),
            minimum_rating=4.0,
        ),
    )


def margin_between(first: float, second: float) -> str:
    difference = abs(float(first) - float(second))
    return format_idr(difference)
