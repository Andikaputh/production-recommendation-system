from __future__ import annotations

from rasa.explanations.generator import build_item_reasons
from rasa.missions.parser import parse_mission_text
from rasa.missions.validation import Mission, Preferences


def test_parser_extracts_budget_categories_and_store_limit() -> None:
    parsed = parse_mission_text(
        "Saya ingin tas, alat tulis, dan botol minum maksimal 250 ribu dari 2 toko"
    )

    assert parsed["requires_confirmation"] is True
    assert parsed["mission"]["max_budget"] == 250_000
    assert parsed["mission"]["max_merchants"] == 2
    assert {"bag", "stationery", "drinkware"}.issubset(parsed["mission"]["required_categories"])


def test_explanation_only_uses_real_features() -> None:
    preferences = Preferences(style=["minimalist"], minimum_rating=4.2)
    mission = Mission("Kuliah", ["bag"], [], 200_000, 2, preferences)
    row = {"category_id": "bag", "category_name": "Tas", "price": 100_000, "rating": 4.7, "style": "minimalist"}

    reasons = build_item_reasons(
        row, {"content": 0.8, "collaborative": 0.0, "affinity": 0.0},
        mission, preferences, {"user_known": False}, {"bag": 150_000},
    )

    codes = {reason["code"] for reason in reasons}
    assert {"required_category", "content_match", "preference_match", "rating_threshold", "price_fit"} == codes
    assert "personalization" not in codes
