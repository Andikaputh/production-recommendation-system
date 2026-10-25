from __future__ import annotations

import pandas as pd

from rasa.missions.validation import Mission, Preferences, minimum_budget, validate_mission


def catalog_frames() -> tuple[pd.DataFrame, pd.DataFrame]:
    catalog = pd.DataFrame([
        {"product_id": "p1", "category_id": "bag", "price": 50_000, "rating": 4.2, "availability_status": "available", "merchant_id": "m1"},
        {"product_id": "p2", "category_id": "stationery", "price": 10_000, "rating": 4.8, "availability_status": "available", "merchant_id": "m1"},
        {"product_id": "p3", "category_id": "bag", "price": 40_000, "rating": 4.5, "availability_status": "unavailable", "merchant_id": "m2"},
    ])
    categories = pd.DataFrame([
        {"category_id": "bag", "category_name": "Tas"},
        {"category_id": "stationery", "category_name": "Alat Tulis"},
    ])
    return catalog, categories


def test_valid_mission_is_normalized() -> None:
    catalog, categories = catalog_frames()
    mission = Mission("  Kuliah harian  ", ["bag"], ["stationery"], 100_000, 1)

    result = validate_mission(mission, catalog, categories)

    assert result.valid is True
    assert result.normalized is not None
    assert result.normalized.goal == "Kuliah harian"


def test_unknown_category_and_overlap_are_rejected() -> None:
    catalog, categories = catalog_frames()
    mission = Mission("Misi", ["bag", "unknown"], ["bag"], 100_000, 2)

    result = validate_mission(mission, catalog, categories)

    assert result.valid is False
    assert {issue.code for issue in result.errors} == {"unknown_category", "category_overlap"}


def test_budget_conflict_is_explained_not_silently_relaxed() -> None:
    catalog, categories = catalog_frames()
    mission = Mission("Paket kuliah", ["bag", "stationery"], [], 20_000, 1)

    result = validate_mission(mission, catalog, categories)

    assert result.valid is True
    assert "budget_conflict" in {issue.code for issue in result.warnings}
    assert minimum_budget(mission, catalog) == 60_000


def test_rating_outside_dataset_scale_is_rejected() -> None:
    catalog, categories = catalog_frames()
    mission = Mission("Cari tas", ["bag"], [], 100_000, 1, Preferences(minimum_rating=5.0))

    result = validate_mission(mission, catalog, categories)

    assert result.valid is False
    assert result.errors[0].code == "rating_out_of_scale"
