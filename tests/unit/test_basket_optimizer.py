from __future__ import annotations

import pandas as pd

from rasa.missions.validation import Mission
from rasa.optimization.basket import optimize_basket


def scored_catalog() -> pd.DataFrame:
    rows = [
        ["bag-1", "Tas A", "bag", "Tas", 90_000, 4.7, "m1", "Toko Satu", 0.9],
        ["bag-2", "Tas B", "bag", "Tas", 60_000, 4.5, "m2", "Toko Dua", 0.7],
        ["pen-1", "Pena A", "stationery", "Alat Tulis", 30_000, 4.8, "m1", "Toko Satu", 0.8],
        ["pen-2", "Pena B", "stationery", "Alat Tulis", 12_000, 4.4, "m2", "Toko Dua", 0.6],
    ]
    frame = pd.DataFrame(rows, columns=[
        "product_id", "product_name", "category_id", "category_name", "price", "rating",
        "merchant_id", "merchant_name", "score",
    ])
    frame["availability_status"] = "available"
    frame["exclusive_group"] = ""
    return frame


def test_optimizer_enforces_budget_categories_and_merchant_limit() -> None:
    scored = scored_catalog()
    mission = Mission("Paket kuliah", ["bag", "stationery"], [], 130_000, 1)

    result = optimize_basket(scored, mission, scored)

    assert result.feasible is True
    assert result.total_price <= 130_000
    assert result.merchant_count == 1
    assert result.required_category_coverage == 1.0
    assert {item.category_id for item in result.items} == {"bag", "stationery"}


def test_optimizer_returns_actionable_infeasible_result() -> None:
    scored = scored_catalog()
    mission = Mission("Paket mustahil", ["bag", "stationery"], [], 20_000, 1)

    result = optimize_basket(scored, mission, scored)

    assert result.feasible is False
    assert result.items == []
    assert result.suggestions
    assert result.diagnostics["infeasibility_analysis"]["minimum_required_budget"] == 72_000
