from __future__ import annotations

from typing import Any

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from rasa.api.app import create_app
from rasa.db.seed import seed_database
from rasa.db.session import reset_engine
from rasa.ranking.ranker import RankedItem, RankResult


class StubRanker:
    def rank(self, catalog: pd.DataFrame, mission, **_: Any) -> RankResult:
        selected = []
        for category_id in mission.required_categories:
            group = catalog[
                (catalog["category_id"] == category_id)
                & (catalog["availability_status"] == "available")
            ]
            if mission.preferences.minimum_rating is not None:
                group = group[group["rating"] >= mission.preferences.minimum_rating]
            if not group.empty:
                selected.append(group.sort_values(["rating", "price"], ascending=[False, True]).iloc[0])
        scored = pd.DataFrame(selected).copy()
        if scored.empty:
            return RankResult([], scored, {"candidate_generation": {}})
        scored["score"] = [0.95 - index * 0.05 for index in range(len(scored))]
        scored["exclusive_group"] = ""
        items = []
        for row in scored.to_dict("records"):
            items.append(RankedItem(
                product_id=str(row["product_id"]), product_name=str(row["product_name"]),
                category_id=str(row["category_id"]), category_name=str(row["category_name"]),
                subcategory=str(row.get("subcategory") or ""), brand=str(row.get("brand") or ""),
                price=float(row["price"]), rating=float(row["rating"]),
                review_count=int(row.get("review_count") or 0), availability_status="available",
                merchant_id=str(row["merchant_id"]), merchant_name=str(row["merchant_name"]),
                merchant_rating=float(row.get("merchant_rating") or 4.5),
                style=str(row.get("style") or ""), color=str(row.get("color") or ""),
                material=str(row.get("material") or ""), score=float(row["score"]),
                components={"mission": 1.0, "quality": 0.8},
                reasons=[{"code": "required_category", "label": "Kategori wajib", "detail": "Sesuai misi", "strength": 1.0}],
                flags={"user_known": False},
            ))
        return RankResult(items, scored, {"candidate_generation": {"n_candidates": len(scored)}})


class StubRegistry:
    ready = True
    error = None
    ranker = StubRanker()
    model_version = "test-model-v1"
    dataset_version = "rasa-synth-1.0.0"
    popularity = None

    def load(self):
        return self

    def status(self) -> dict[str, Any]:
        return {
            "ready": True,
            "model_version": self.model_version,
            "dataset_version": self.dataset_version,
            "trained_at": "2026-10-24T00:00:00Z",
            "error": None,
        }


@pytest.fixture()
def client(tmp_path, monkeypatch):
    database_url = f"sqlite:///{(tmp_path / 'test.db').as_posix()}"
    monkeypatch.setenv("RASA_DATABASE_URL", database_url)
    monkeypatch.setenv("RASA_ENV", "test")
    reset_engine(database_url)
    seed_database(drop=True, include_events=False)
    app = create_app(StubRegistry())
    with TestClient(app) as test_client:
        yield test_client
    reset_engine()


def test_health_catalog_and_openapi(client: TestClient) -> None:
    health = client.get("/health")
    categories = client.get("/api/v1/catalog/categories")
    openapi = client.get("/openapi.json")

    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert len(categories.json()["items"]) == 10
    assert "/api/v1/recommendations" in openapi.json()["paths"]


def test_invalid_payload_returns_safe_structured_error(client: TestClient) -> None:
    response = client.post("/api/v1/recommendations", json={
        "mission": {
            "goal": "x", "required_categories": [], "optional_categories": [],
            "max_budget": -1, "max_merchants": 0,
        }
    })

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert "traceback" not in response.text.lower()

    feedback = client.post("/api/v1/feedback", json={
        "session_id": "integration-session", "event_type": "impression"
    })
    assert feedback.status_code == 422


def test_recommendation_to_feedback_to_analytics_flow(client: TestClient) -> None:
    payload = {
        "mission": {
            "goal": "Paket kuliah", "required_categories": ["bag", "stationery"],
            "optional_categories": [], "max_budget": 1_000_000, "max_merchants": 10,
        },
        "preferences": {"style": [], "colors": [], "brands": [], "minimum_rating": 4.0},
        "context": {"session_id": "integration-session", "top_k": 10},
    }
    recommendation = client.post("/api/v1/recommendations", json=payload)

    assert recommendation.status_code == 200
    body = recommendation.json()
    assert body["status"] == "success"
    assert body["basket"]["feasible"] is True
    assert body["basket"]["total_price"] <= payload["mission"]["max_budget"]
    assert body["basket"]["required_category_coverage"] == 1.0
    assert body["explanations"]

    product_id = body["basket"]["items"][0]["product_id"]
    feedback = client.post("/api/v1/feedback", json={
        "session_id": "integration-session", "product_id": product_id,
        "event_type": "save", "metadata": {"surface": "test"},
    })
    assert feedback.status_code == 200
    assert feedback.json()["status"] == "recorded"

    analytics = client.get("/api/v1/analytics/summary?days=30")
    assert analytics.status_code == 200
    assert analytics.json()["sample_sizes"]["recommendation_requests"] == 1
    assert analytics.json()["sample_sizes"]["feedback_events"] == 1
