"""Basket-quality metrics required by PRD section 11.3."""

from __future__ import annotations

from collections import Counter
from typing import Any

import numpy as np

from rasa.optimization.basket import BasketResult


def summarize_baskets(
    results: list[BasketResult],
    *,
    substitution_success: float | None = None,
) -> dict[str, Any]:
    if not results:
        return {}
    feasible = [result for result in results if result.feasible]
    infeasible = [result for result in results if not result.feasible]
    total_prices = [result.total_price for result in feasible]
    utilizations = [
        result.total_price / max(1.0, result.total_price + result.budget_remaining)
        for result in feasible
    ]
    relevance = [
        float(np.mean([item.score for item in result.items])) if result.items else 0.0
        for result in feasible
    ]
    availabilities = [
        1.0 if all(item.price > 0 for item in result.items) else 0.0 for result in feasible
    ]
    latencies = [result.solve_time_ms for result in results]
    explained = [
        result for result in infeasible
        if result.suggestions or result.diagnostics.get("infeasibility_analysis")
    ]
    return {
        "n_missions": len(results),
        "budget_feasibility_rate": round(len(feasible) / len(results), 4),
        "infeasible_mission_rate": round(len(infeasible) / len(results), 4),
        "required_category_coverage": round(
            float(np.mean([result.required_category_coverage for result in feasible])) if feasible else 0.0, 4
        ),
        "availability_feasibility": round(float(np.mean(availabilities)) if availabilities else 0.0, 4),
        "avg_merchant_count": round(float(np.mean([result.merchant_count for result in feasible])) if feasible else 0.0, 2),
        "merchant_count_distribution": dict(Counter(result.merchant_count for result in feasible)),
        "budget_utilization": round(float(np.mean(utilizations)) if utilizations else 0.0, 4),
        "avg_basket_total": round(float(np.mean(total_prices)) if total_prices else 0.0, 2),
        "basket_relevance": round(float(np.mean(relevance)) if relevance else 0.0, 4),
        "substitution_success": round(float(substitution_success), 4) if substitution_success is not None else None,
        "infeasibility_explanation_rate": round(len(explained) / len(infeasible), 4) if infeasible else None,
        "solver_latency_ms": {
            "mean": round(float(np.mean(latencies)), 2) if latencies else 0.0,
            "p95": round(float(np.percentile(latencies, 95)), 2) if latencies else 0.0,
        },
        "solver_usage": dict(Counter(result.solver for result in results)),
        "all_feasible_constraints_valid": all(
            result.total_price <= (result.total_price + result.budget_remaining) + 1e-6
            and result.required_category_coverage == 1.0
            for result in feasible
        ),
    }
