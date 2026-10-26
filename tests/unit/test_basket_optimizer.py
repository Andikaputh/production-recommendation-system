from __future__ import annotations

import pandas as pd

from rasa.missions.validation import Mission
from rasa.optimization.basket import optimize_basket


def scored_catalog() -> pd.DataFrame:
    rows = [
        ["bag-1", "Bag A", "bag", "Bags", 90_000, 4.7, "m1", "Store One", 0.9],
        ["bag-2", "Bag B", "bag", "Bags", 60_000, 4.5, "m2", "Store Two", 0.7],
        ["pen-1", "Pen A", "stationery", "Stationery", 30_000, 4.8, "m1", "Store One", 0.8],
        ["pen-2", "Pen B", "stationery", "Stationery", 12_000, 4.4, "m2", "Store Two", 0.6],
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


def test_pruning_keeps_low_score_affordable_route():
    template = scored_catalog().iloc[0].to_dict()
    rows = []
    for category in ["bag", "stationery"]:
        for i in range(15):
            rows.append({**template, "product_id": f"{category}-{i}", "category_id": category,
                         "price": 100 if i < 14 else 10, "score": 1 if i < 14 else .1})
    frame = pd.DataFrame(rows)
    result = optimize_basket(frame, Mission("Anggaran ketat", ["bag", "stationery"], [], 25, 1), frame)
    assert result.feasible and result.total_price == 20


def test_optimizer_fallback_respects_exclusion_and_stock(monkeypatch):
    import rasa.optimization.basket as module
    monkeypatch.setattr(module, "PULP_AVAILABLE", False)
    frame = scored_catalog()
    frame.loc[frame.product_id.isin(["bag-1", "pen-1"]), "exclusive_group"] = "same-use"
    frame.loc[frame.product_id == "bag-2", "availability_status"] = "unavailable"
    result = optimize_basket(frame, Mission("Eksklusi stok", ["bag", "stationery"], [], 150000, 2), frame)
    assert result.feasible
    assert {i.product_id for i in result.items} == {"bag-1", "pen-2"}


def test_availability_metric_uses_inventory_validation():
    from rasa.evaluation.basket_metrics import summarize_baskets
    from rasa.optimization.basket import naive_independent_basket
    frame = scored_catalog()
    frame["availability_status"] = "unavailable"
    # An intentionally unconstrained baseline can return positive prices but invalid inventory.
    baseline = naive_independent_basket(frame, Mission("Baseline stok", ["bag"], [], 200000, 2))
    assert summarize_baskets([baseline])["availability_feasibility"] == 0
    assert not summarize_baskets([baseline])["all_feasible_constraints_valid"]
