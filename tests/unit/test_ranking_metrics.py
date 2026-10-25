from __future__ import annotations

import pytest

from rasa.evaluation.ranking_metrics import (
    average_precision_at_k,
    bootstrap_ci,
    evaluate_recommendation,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
)


def test_ranking_metrics_use_top_k_and_relevance_set() -> None:
    recommended = ["a", "x", "b", "y"]
    relevant = {"a", "b", "c"}

    assert precision_at_k(recommended, relevant, 4) == 0.5
    assert recall_at_k(recommended, relevant, 4) == pytest.approx(2 / 3)
    assert 0 < ndcg_at_k(recommended, relevant, 4) < 1
    assert average_precision_at_k(recommended, relevant, 4) == pytest.approx((1 + 2 / 3) / 3)


def test_empty_relevance_is_safe() -> None:
    metrics = evaluate_recommendation(["a"], [], k=10)
    assert all(value == 0 for value in metrics.values())


def test_bootstrap_is_reproducible() -> None:
    first = bootstrap_ci([0.1, 0.2, 0.4], n_boot=100, seed=42)
    second = bootstrap_ci([0.1, 0.2, 0.4], n_boot=100, seed=42)
    assert first == second
