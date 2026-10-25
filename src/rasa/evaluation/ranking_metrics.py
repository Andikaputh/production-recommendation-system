"""Offline ranking metrics with an explicit relevance definition.

Relevance means a positive event in the temporal holdout after excluding
products already seen in training.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence

import numpy as np


def _hits(recommended: Sequence[str], relevant: set[str], k: int) -> list[int]:
    return [1 if product_id in relevant else 0 for product_id in recommended[:k]]


def precision_at_k(recommended: Sequence[str], relevant: set[str], k: int) -> float:
    if k <= 0:
        return 0.0
    return sum(_hits(recommended, relevant, k)) / float(k)


def recall_at_k(recommended: Sequence[str], relevant: set[str], k: int) -> float:
    if not relevant:
        return 0.0
    return sum(_hits(recommended, relevant, k)) / float(len(relevant))


def ndcg_at_k(recommended: Sequence[str], relevant: set[str], k: int) -> float:
    hits = _hits(recommended, relevant, k)
    dcg = sum(hit / math.log2(position + 2) for position, hit in enumerate(hits))
    ideal_hits = [1] * min(len(relevant), k)
    idcg = sum(hit / math.log2(position + 2) for position, hit in enumerate(ideal_hits))
    return dcg / idcg if idcg > 0 else 0.0


def average_precision_at_k(recommended: Sequence[str], relevant: set[str], k: int) -> float:
    hits = _hits(recommended, relevant, k)
    if not relevant or sum(hits) == 0:
        return 0.0
    running = 0
    precision_sum = 0.0
    for position, hit in enumerate(hits, start=1):
        if hit:
            running += 1
            precision_sum += running / position
    return precision_sum / min(len(relevant), k)


def reciprocal_rank_at_k(recommended: Sequence[str], relevant: set[str], k: int) -> float:
    for position, product_id in enumerate(recommended[:k], start=1):
        if product_id in relevant:
            return 1.0 / position
    return 0.0


def hit_rate_at_k(recommended: Sequence[str], relevant: set[str], k: int) -> float:
    return 1.0 if any(product_id in relevant for product_id in recommended[:k]) else 0.0


def evaluate_recommendation(
    recommended: Sequence[str],
    relevant: Iterable[str],
    k: int = 10,
) -> dict[str, float]:
    relevant_set = set(relevant)
    return {
        f"precision@{k}": precision_at_k(recommended, relevant_set, k),
        f"recall@{k}": recall_at_k(recommended, relevant_set, k),
        f"ndcg@{k}": ndcg_at_k(recommended, relevant_set, k),
        f"map@{k}": average_precision_at_k(recommended, relevant_set, k),
        "mrr": reciprocal_rank_at_k(recommended, relevant_set, k),
        f"hit_rate@{k}": hit_rate_at_k(recommended, relevant_set, k),
    }


def aggregate_metrics(rows: list[dict[str, float]], metric_names: list[str] | None = None) -> dict[str, float]:
    if not rows:
        return {}
    names = metric_names or list(rows[0].keys())
    return {
        name: float(np.mean([row.get(name, 0.0) for row in rows]))
        for name in names
    }


def bootstrap_ci(
    values: list[float],
    *,
    n_boot: int = 1000,
    confidence: float = 0.95,
    seed: int = 42,
) -> dict[str, float] | None:
    if not values:
        return None
    rng = np.random.default_rng(seed)
    array = np.asarray(values, dtype=float)
    samples = rng.choice(array, size=(n_boot, len(array)), replace=True).mean(axis=1)
    alpha = (1 - confidence) / 2
    return {
        "mean": float(array.mean()),
        "ci_low": float(np.quantile(samples, alpha)),
        "ci_high": float(np.quantile(samples, 1 - alpha)),
    }
