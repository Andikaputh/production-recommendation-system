"""Select hybrid weights through validation rather than intuition.

Grid search uses the validation split, then freezes weights in
``artifacts/models/hybrid_config.json`` so the test set never determines the
configuration.
"""

from __future__ import annotations

import itertools
from typing import Any

import numpy as np
import pandas as pd

from rasa.config import settings
from rasa.data.schema import POSITIVE_EVENTS
from rasa.evaluation.ranking_metrics import aggregate_metrics, bootstrap_ci, evaluate_recommendation
from rasa.ranking.ranker import HybridRanker, simulate_mission_for_user
from rasa.utils import iso_now


def _weight_combinations() -> list[dict[str, float]]:
    grid = settings.get("ranking.weight_grid", {})
    keys = ["collaborative", "content", "mission", "quality", "affinity"]
    values = [list(grid.get(key, [0.0])) for key in keys]
    combinations: list[dict[str, float]] = []
    seen: set[tuple[float, ...]] = set()
    for combination in itertools.product(*values):
        total = sum(combination)
        if total <= 0:
            continue
        normalized = tuple(round(value / total, 4) for value in combination)
        if normalized in seen:
            continue
        seen.add(normalized)
        combinations.append(dict(zip(keys, normalized, strict=False)))
    return combinations


def tune_weights(
    ranker: HybridRanker,
    catalog: pd.DataFrame,
    users: pd.DataFrame,
    train: pd.DataFrame,
    validation: pd.DataFrame,
    *,
    k: int = 10,
    max_users: int = 180,
    seed: int = 42,
) -> dict[str, Any]:
    positives_train = train[train["event_type"].isin(POSITIVE_EVENTS)]
    seen_by_user = positives_train.groupby("user_id")["product_id"].agg(set).to_dict()
    event_weights = settings.get("features.event_weights", {})
    history_by_user: dict[str, dict[str, float]] = {}
    for row in positives_train.itertuples():
        bucket = history_by_user.setdefault(row.user_id, {})
        bucket[row.product_id] = bucket.get(row.product_id, 0.0) + float(
            event_weights.get(row.event_type, 1.0) or 1.0
        )
    relevant_by_user = {
        user_id: set(group["product_id"]) - seen_by_user.get(user_id, set())
        for user_id, group in validation[validation["event_type"].isin(POSITIVE_EVENTS)].groupby("user_id")
    }
    relevant_by_user = {user_id: items for user_id, items in relevant_by_user.items() if items}

    user_rows = {
        row["user_id"]: row for row in users.to_dict("records") if row["user_id"] in relevant_by_user
    }
    candidate_users = sorted(relevant_by_user)[:max_users]

    prepared: list[dict[str, Any]] = []
    for user_id in candidate_users:
        user_row = user_rows.get(user_id)
        if user_row is None:
            continue
        mission = simulate_mission_for_user(pd.Series(user_row), catalog)
        mission_products = set(
            catalog.loc[catalog["category_id"].isin(mission.all_categories), "product_id"]
        )
        relevant = relevant_by_user[user_id] & mission_products
        if not relevant:
            continue
        result = ranker.rank(
            catalog,
            mission,
            user_id=user_id,
            history_weights=history_by_user.get(user_id),
            strategy="hybrid_mission",
            top_k=k,
            exclude_product_ids=seen_by_user.get(user_id, set()),
        )
        if result.scored.empty:
            continue
        frame = result.scored[["product_id", "component_collaborative", "component_content",
                               "component_mission", "component_quality", "component_affinity"]].copy()
        prepared.append({
            "user_id": user_id,
            "frame": frame,
            "relevant": relevant,
        })

    combinations = _weight_combinations()
    scores: list[dict[str, Any]] = []
    for weights in combinations:
        metric_rows: list[dict[str, float]] = []
        for item in prepared:
            frame = item["frame"]
            score = (
                weights["collaborative"] * frame["component_collaborative"].to_numpy()
                + weights["content"] * frame["component_content"].to_numpy()
                + weights["mission"] * frame["component_mission"].to_numpy()
                + weights["quality"] * frame["component_quality"].to_numpy()
                + weights["affinity"] * frame["component_affinity"].to_numpy()
            )
            order = np.argsort(-score, kind="stable")[:k]
            recommended = frame["product_id"].to_numpy()[order].tolist()
            metric_rows.append(evaluate_recommendation(recommended, item["relevant"], k=k))
        aggregated = aggregate_metrics(metric_rows, [f"ndcg@{k}", f"recall@{k}", f"precision@{k}"])
        scores.append({
            "weights": weights,
            "metrics": aggregated,
            "n_users": len(metric_rows),
        })

    scores.sort(key=lambda row: (row["metrics"].get(f"ndcg@{k}", 0), row["metrics"].get(f"recall@{k}", 0)), reverse=True)
    best = scores[0]
    ndcg_values = []
    for item in prepared:
        frame = item["frame"]
        score = (
            best["weights"]["collaborative"] * frame["component_collaborative"].to_numpy()
            + best["weights"]["content"] * frame["component_content"].to_numpy()
            + best["weights"]["mission"] * frame["component_mission"].to_numpy()
            + best["weights"]["quality"] * frame["component_quality"].to_numpy()
            + best["weights"]["affinity"] * frame["component_affinity"].to_numpy()
        )
        order = np.argsort(-score, kind="stable")[:k]
        recommended = frame["product_id"].to_numpy()[order].tolist()
        ndcg_values.append(evaluate_recommendation(recommended, item["relevant"], k=k)[f"ndcg@{k}"])
    confidence = bootstrap_ci(ndcg_values, seed=seed)

    default_weights = {key: float(value) for key, value in settings.get("ranking.weights", {}).items()}
    total_default = sum(default_weights.values()) or 1.0
    default_normalized = {key: value / total_default for key, value in default_weights.items()}

    return {
        "selected_at": iso_now(),
        "objective": f"mean ndcg@{k} on validation split",
        "seed": seed,
        "k": k,
        "n_users": len(prepared),
        "n_weight_combinations": len(combinations),
        "weights": best["weights"],
        "selected_metrics": best["metrics"],
        "selected_ndcg_ci": confidence,
        "default_weights": default_normalized,
        "top_10": scores[:10],
        "validation_set": {
            "n_users": len(prepared),
            "fraction": settings.get("split.validation_fraction", 0.15),
            "note": "Validation uses the final portion of each user's training data; the test split is not used.",
        },
    }
