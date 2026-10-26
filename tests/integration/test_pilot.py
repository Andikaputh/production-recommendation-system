from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from rasa.api.app import create_app
from rasa.db.models import Category, PilotCatalog, PilotEvent, Product
from rasa.db.session import init_db, reset_engine, session_scope
from rasa.utils import utcnow

SID = {"X-Session-ID": "test-session-secret-123456"}
ADMIN = {"Authorization": "Bearer test-admin-token"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'pilot.db').as_posix()}"
    monkeypatch.setenv("RASA_DATABASE_URL", url)
    monkeypatch.setenv("RASA_MODE", "pilot")
    monkeypatch.setenv("RASA_ENV", "test")
    monkeypatch.setenv("RASA_ADMIN_TOKEN", "test-admin-token")
    monkeypatch.delenv("RASA_PILOT_SHIPPING_IDR", raising=False)
    reset_engine(url)
    init_db()
    with session_scope() as db:
        db.add_all([Category(category_id=c, category_name=c) for c in ["bag", "stationery"]])
    # Avoid artifact loading: these routes deliberately use transparent rules for new SKUs.
    app = create_app()
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    reset_engine()


def catalog_text():
    stamp = utcnow().isoformat() + "Z"
    return "product_id,product_name,category_id,merchant_id,price,stock,updated_at,style,color\n" + "\n".join([
        f"bag-a,Tas A,bag,pilot-store,100000,5,{stamp},minimalist,black",
        f"bag-b,Tas B,bag,pilot-store,120000,3,{stamp},natural,white",
        f"pen-a,Pena A,stationery,pilot-store,10000,20,{stamp},minimalist,black",
    ])


def load(client, text=None, synthetic=False):
    response = client.post("/api/v1/pilot/catalog/import", headers=ADMIN, json={"csv_text": text or catalog_text(), "synthetic": synthetic, "dry_run": False})
    assert response.status_code == 200, response.text
    return response.json()


def start(client, budget=200000, mid="mission-12345678"):
    return client.post("/api/v1/pilot/missions", headers=SID, json={"mission_id": mid, "mission": {"goal": "Paket awal kuliah", "required_categories": ["bag", "stationery"], "max_budget": budget}, "preferences": {"style": ["minimalist"]}})


def action(client, kind, revision=1, **kwargs):
    return client.post(f"/api/v1/pilot/missions/mission-12345678/{kind}", headers=SID, json={"revision": revision, **kwargs})


def test_import_errors_are_atomic_actionable_and_protected(client):
    assert client.post("/api/v1/recommendations", json={}).status_code == 409
    assert client.post("/api/v1/pilot/catalog/import", json={"csv_text": "x"}).status_code == 401
    report = load(client, catalog_text().replace("100000", "NaN").replace("pen-a", "bag-a"))
    assert not report["valid"] and report["written"] == 0
    assert {e["field"] for e in report["errors"]} >= {"price", "product_id"}
    with session_scope() as db:
        assert list(db.scalars(select(Product))) == []


def test_dry_run_writes_nothing(client):
    result = client.post("/api/v1/pilot/catalog/import", headers=ADMIN, json={"csv_text": catalog_text()}).json()
    assert result["valid"] and result["written"] == 0
    assert client.get("/readyz").status_code == 503


def test_complete_mission_dedup_accept_and_handoff(client):
    assert load(client)["written"] == 3
    assert client.get("/readyz").status_code == 200
    first = start(client).json()
    assert first["basket"]["feasible"] and first["source"] == "pilot"
    assert first["basket"]["costs"]["total"] is None
    assert not first["basket"]["costs"]["final_budget_confirmed"]
    assert start(client).json()["mission_id"] == first["mission_id"]
    assert action(client, "handoff").status_code == 409
    assert action(client, "accept").status_code == 200
    assert action(client, "accept").status_code == 200
    assert action(client, "handoff").json()["handoff"]["sent"] is False
    assert action(client, "handoff").status_code == 200
    with session_scope() as db:
        assert len(list(db.scalars(select(PilotEvent)))) == 4
    analytics = client.get("/api/v1/pilot/analytics", headers=ADMIN).json()
    assert analytics["mission_completion_rate"] == 1
    assert analytics["confirmed_orders"] is None
    assert client.get("/api/v1/pilot/analytics").status_code == 401
    assert client.get("/api/v1/analytics/summary").status_code == 401


def test_infeasible_mission_is_recorded(client):
    load(client)
    body = start(client, budget=1).json()
    assert not body["basket"]["feasible"]
    assert "110,000" in body["basket"]["suggestions"][0]
    assert action(client, "accept").status_code == 409
    assert client.get("/api/v1/pilot/analytics", headers=ADMIN).json()["infeasible_rate"] == 1


def test_replace_validates_full_basket_and_invalidates_old_acceptance(client):
    load(client)
    start(client)
    action(client, "accept")
    swapped = action(client, "replace", product_id="bag-a", replacement_id="bag-b")
    assert swapped.status_code == 200, swapped.text
    assert swapped.json()["revision"] == 2
    assert swapped.json()["basket"]["total_price"] == 130000
    assert action(client, "accept").status_code == 409
    assert action(client, "handoff", revision=2).status_code == 409
    assert action(client, "accept", revision=2).status_code == 200


def test_replace_rejects_budget_and_category_violation(client):
    load(client)
    start(client, budget=115000)
    assert action(client, "replace", product_id="bag-a", replacement_id="bag-b").status_code == 409
    assert action(client, "replace", product_id="bag-a", replacement_id="pen-a").status_code == 422


@pytest.mark.parametrize("change", ["price", "stock", "stock_count", "stale"])
def test_confirmation_rechecks_live_database(client, change):
    load(client)
    start(client)
    with session_scope() as db:
        if change == "stale":
            db.get(PilotCatalog, "pilot-store").imported_at = utcnow() - timedelta(days=2)
        else:
            p = db.get(Product, "bag-a")
            if change == "price":
                p.price = 100001
            elif change == "stock_count":
                p.attributes = {**p.attributes, "stock": 0}
            else:
                p.availability_status = "unavailable"
    assert action(client, "accept").status_code == 409


def test_known_shipping_is_reserved_and_data_sources_separate(client, monkeypatch):
    load(client, synthetic=True)
    monkeypatch.setenv("RASA_PILOT_SHIPPING_IDR", "10000")
    body = start(client, budget=115000).json()
    assert body["source"] == "demo"
    assert not body["basket"]["feasible"]
    assert client.get("/api/v1/pilot/analytics", headers=ADMIN).json()["denominators"]["created_missions"] == 0


def test_session_isolation_restart_and_retired_inventory(client):
    load(client)
    first = start(client).json()
    other = client.post("/api/v1/pilot/missions/mission-12345678/accept", headers={"X-Session-ID": "another-secret-session"}, json={"revision": 1})
    assert other.status_code == 404
    # Separate DB session simulates restart of in-memory state: persisted snapshots survive.
    from rasa.services.pilot import owner
    with session_scope() as db:
        assert owner(db, first["mission_id"], SID["X-Session-ID"]).snapshot["feasible"]
    load(client, "\n".join(catalog_text().splitlines()[:1] + catalog_text().splitlines()[2:]))
    assert action(client, "accept").status_code == 409


def test_stale_wrong_merchant_and_malformed_import(client):
    text = catalog_text().replace("pilot-store", "other")
    assert not load(client, text)["valid"]
    text = catalog_text().replace(utcnow().strftime("%Y-%m-%d"), "2000-01-01")
    assert not load(client, text)["valid"]
    assert not load(client, "product_id,price\nx,0")["valid"]
