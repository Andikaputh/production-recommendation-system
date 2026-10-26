"""Single-merchant pilot: local imports, versioned baskets and factual funnel events."""
from __future__ import annotations

import csv
import hashlib
import io
import math
import os
import re
import secrets
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pandas as pd
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from rasa.api.deps import get_db
from rasa.api.schemas import MissionIn, PreferencesIn
from rasa.config import settings
from rasa.db.models import Category, Merchant, PilotCatalog, PilotEvent, PilotMission, Product
from rasa.missions.validation import Mission
from rasa.optimization.basket import optimize_basket
from rasa.services.catalog import CatalogService
from rasa.utils import utcnow

router = APIRouter(prefix="/api/v1/pilot", tags=["pilot"])
COLUMNS = {"product_id", "product_name", "category_id", "merchant_id", "price", "stock", "updated_at"}


def enabled() -> bool:
    return os.getenv("RASA_MODE", "demo") == "pilot"


def merchant_id() -> str:
    return os.getenv("RASA_PILOT_MERCHANT", "pilot-store")


def require_admin(authorization: str = Header(default="")) -> None:
    token = os.getenv("RASA_ADMIN_TOKEN", "")
    if not token or not secrets.compare_digest(authorization, f"Bearer {token}"):
        raise HTTPException(401, "Token admin diperlukan untuk impor dan analitik.")


def shipping() -> float | None:
    raw = os.getenv("RASA_PILOT_SHIPPING_IDR", "")
    if not raw:
        return None
    value = float(raw)
    if not math.isfinite(value) or value < 0:
        raise ValueError("RASA_PILOT_SHIPPING_IDR harus angka nonnegatif.")
    return value


def parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Gunakan waktu ISO 8601 dengan zona waktu, contoh 2026-10-26T08:00:00Z.")
    return parsed.astimezone(UTC).replace(tzinfo=None)


def stale(value: datetime) -> bool:
    return value < utcnow() - timedelta(hours=int(os.getenv("RASA_CATALOG_TTL_HOURS", "24")))


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class CatalogImport(StrictInput):
    csv_text: str = Field(min_length=1, max_length=60000)
    synthetic: bool = True
    dry_run: bool = True


def import_catalog(db: Session, payload: CatalogImport) -> dict:
    if not payload.synthetic and not enabled():
        raise HTTPException(409, "Impor data nyata memerlukan RASA_MODE=pilot.")
    reader = csv.DictReader(io.StringIO(payload.csv_text.lstrip("\ufeff")))
    missing = sorted(COLUMNS - set(reader.fieldnames or []))
    errors, records, seen = [], [], set()
    if missing:
        return {"valid": False, "errors": [{"row": 1, "field": "header", "message": f"Kolom wajib belum ada: {', '.join(missing)}"}]}
    if len(reader.fieldnames) != len(set(reader.fieldnames)):
        return {"valid": False, "errors": [{"row": 1, "field": "header", "message": "Nama kolom tidak boleh duplikat."}], "written": 0}
    categories = set(db.scalars(select(Category.category_id)))
    for line, row in enumerate(reader, 2):
        if None in row or any(value is None for value in row.values()):
            errors.append({"row": line, "field": "csv", "message": "Jumlah kolom tidak sesuai header. Periksa koma dan tanda kutip."})
            continue
        issues = []
        def issue(field, message, issues=issues, line=line):
            issues.append({"row": line, "field": field, "message": message})
        pid = row.get("product_id", "").strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,50}", pid) or pid in seen:
            issue("product_id", "ID harus unik, 1-50 huruf/angka/strip/garis bawah.")
        seen.add(pid)
        existing = db.get(Product, pid)
        if existing and existing.merchant_id != merchant_id():
            issue("product_id", "ID dimiliki merchant lain; gunakan ID baru.")
        if row.get("merchant_id") != merchant_id():
            issue("merchant_id", f"Harus {merchant_id()} untuk pilot ini.")
        if row.get("category_id") not in categories:
            issue("category_id", f"Pilih kategori dikenal: {', '.join(sorted(categories))}")
        name = row.get("product_name", "").strip()
        if not 1 <= len(name) <= 220:
            issue("product_name", "Nama wajib, maksimal 220 karakter.")
        try:
            price = float(row["price"])
            if not math.isfinite(price) or price <= 0 or price > 50_000_000 or price != int(price):
                raise ValueError
        except (ValueError, TypeError):
            price = 0
            issue("price", "Gunakan rupiah bulat positif, maksimal 50 juta, tanpa pemisah ribuan.")
        try:
            stock = int(row["stock"])
            if stock < 0 or stock > 1_000_000:
                raise ValueError
        except (ValueError, TypeError):
            stock = 0
            issue("stock", "Stok harus bilangan bulat 0-1000000.")
        try:
            updated = parse_time(row["updated_at"])
            if stale(updated) or updated > utcnow() + timedelta(minutes=5):
                raise ValueError("Waktu data kedaluwarsa atau di masa depan; minta pembaruan dari merchant.")
        except (ValueError, TypeError) as exc:
            updated = utcnow()
            issue("updated_at", str(exc) or "Waktu ISO 8601 dengan zona waktu diperlukan.")
        errors.extend(issues)
        if not issues:
            records.append((row, pid, name, price, stock, updated))
    if not records and not errors:
        errors.append({"row": 2, "field": "catalog", "message": "Katalog tidak boleh kosong."})
    if errors:
        return {"valid": False, "errors": errors, "written": 0}
    if payload.dry_run:
        return {"valid": True, "rows": len(records), "written": 0, "dry_run": True}
    if db.get(Merchant, merchant_id()) is None:
        db.add(Merchant(merchant_id=merchant_id(), merchant_name=os.getenv("RASA_PILOT_MERCHANT_NAME", "Merchant pilot"), rating=0, is_low_history=True))
        db.flush()
    # A complete snapshot retires omitted items without deleting historical references.
    for product in db.scalars(select(Product).where(Product.merchant_id == merchant_id())):
        product.availability_status = "unavailable"
    for row, pid, name, price, stock, updated in records:
        product = db.get(Product, pid) or Product(product_id=pid)
        product.product_name, product.category_id, product.merchant_id = name, row["category_id"], merchant_id()
        product.price, product.rating, product.review_count = price, 0.0, 0
        product.description = row.get("description", "") or name
        product.brand, product.subcategory = row.get("brand", ""), ""
        product.availability_status = "available" if stock > 0 else "unavailable"
        product.attributes = {"stock": stock, "updated_at": updated.isoformat() + "Z", "pilot": True,
                              "style": row.get("style", ""), "color": row.get("color", ""), "synthetic": payload.synthetic}
        db.add(product)
    batch = db.get(PilotCatalog, merchant_id()) or PilotCatalog(merchant_id=merchant_id())
    batch.imported_at, batch.synthetic = utcnow(), payload.synthetic
    batch.checksum = hashlib.sha256(payload.csv_text.encode()).hexdigest()
    db.add(batch)
    db.flush()
    return {"valid": True, "written": len(records), "checksum": batch.checksum, "imported_at": batch.imported_at.isoformat() + "Z", "synthetic": batch.synthetic}


def current_catalog(db: Session) -> tuple[pd.DataFrame, str]:
    service = CatalogService().load(db)
    if not enabled():
        return service.catalog, "test" if settings.environment == "test" else "demo"
    batch = db.get(PilotCatalog, merchant_id())
    if batch is None or stale(batch.imported_at):
        raise HTTPException(409, "Katalog pilot belum diimpor atau kedaluwarsa. Minta merchant memperbarui katalog.")
    frame = service.catalog[service.catalog["merchant_id"] == merchant_id()].copy()
    frame = frame[frame["attributes"].map(lambda a: a.get("pilot", False) and not stale(parse_time(a["updated_at"])))]
    frame.loc[frame["attributes"].map(lambda a: a.get("stock", 0) < 1), "availability_status"] = "unavailable"
    if frame.empty:
        raise HTTPException(409, "Seluruh baris katalog telah kedaluwarsa.")
    return frame, "demo" if batch.synthetic else "pilot"


def scored_catalog(frame: pd.DataFrame, mission: Mission) -> pd.DataFrame:
    frame = frame[(frame["availability_status"] == "available") & frame["category_id"].isin(mission.all_categories)].copy()
    if mission.preferences.minimum_rating is not None:
        frame = frame[frame["rating"] >= mission.preferences.minimum_rating]
    if mission.preferences.max_item_price is not None:
        frame = frame[frame["price"] <= mission.preferences.max_item_price]
    # Transparent pilot rule baseline works for unseen merchant SKUs without synthetic CF artifacts.
    frame["score"] = 0.5 + 0.3 * frame["style"].isin(mission.preferences.style).astype(float) + 0.2 * frame["color"].isin(mission.preferences.colors).astype(float)
    return frame


def costs(subtotal: float, budget: float) -> dict:
    fee = shipping()
    total = subtotal + fee if fee is not None else None
    return {"subtotal": subtotal, "shipping": fee, "total": total,
            "remaining": budget - total if total is not None else budget - subtotal,
            "final_budget_confirmed": total is not None and total <= budget,
            "notice": "Ongkir belum diketahui; total akhir belum dapat dipastikan." if fee is None else "Biaya tetap pilot, belum ada integrasi logistik. Tidak ada biaya lain dalam konfigurasi pilot."}


def snapshot(db: Session, mission: Mission, ids: list[str] | None = None) -> dict:
    frame, source = current_catalog(db)
    scored = scored_catalog(frame, mission)
    subtotal_budget = max(0, mission.max_budget - (shipping() or 0))
    product_mission = replace(mission, max_budget=subtotal_budget, max_merchants=1 if enabled() else mission.max_merchants)
    if ids is None:
        basket = optimize_basket(scored, product_mission, frame).to_dict()
    else:
        selected = scored[scored["product_id"].isin(ids)].copy()
        # Restrict to the complete user-selected basket; never silently replace its other items.
        basket = optimize_basket(selected, product_mission, frame).to_dict()
        basket["feasible"] = basket["feasible"] and len(ids) == len(set(ids)) and set(ids) == {i["product_id"] for i in basket["items"]}
    basket["costs"] = costs(basket["total_price"], mission.max_budget)
    basket["source"] = source
    basket["scoring_version"] = "pilot-rules-v1"
    basket["explanation"] = "Skor = 0,5 dasar + 0,3 kecocokan gaya + 0,2 kecocokan warna. Optimasi memilih satu barang per kebutuhan wajib, membatasi stok, anggaran barang, toko, dan grup eksklusif. Rating impor belum tersedia; jangan mengasumsikan rating tinggi."
    basket["tradeoff"] = "Pilihan dengan skor tertinggi per kategori dapat melampaui anggaran; kombinasi yang layak bisa memiliki skor lebih rendah."
    options = scored.sort_values(["score", "price", "product_id"], ascending=[False, True, True])
    basket["options"] = {str(cat): group[["product_id", "product_name", "price"]].to_dict("records") for cat, group in options.groupby("category_id")}
    if not basket["feasible"]:
        mins = scored.groupby("category_id")["price"].min()
        missing = sorted(set(mission.required_categories) - set(mins.index))
        lower = float(sum(mins.get(c, 0) for c in mission.required_categories)) + (shipping() or 0)
        basket["suggestions"] = ([f"Belum ada stok atau metadata sesuai filter untuk: {', '.join(missing)}. Ubah kebutuhan atau filter rating."] if missing else [f"Batas bawah biaya kebutuhan wajib Rp{lower:,.0f}. Coba anggaran lebih besar atau kurangi kebutuhan wajib; batas ini belum menjamin kombinasi layak."])
    return basket


class MissionStart(StrictInput):
    mission_id: str = Field(pattern=r"^[A-Za-z0-9_-]{8,80}$")
    mission: MissionIn
    preferences: PreferencesIn = Field(default_factory=PreferencesIn)


class BasketAction(StrictInput):
    revision: int = Field(ge=1)
    product_id: str | None = Field(default=None, max_length=50)
    replacement_id: str | None = Field(default=None, max_length=50)


def owner(db: Session, mid: str, sid: str) -> PilotMission:
    row = db.get(PilotMission, mid)
    if not row or not secrets.compare_digest(row.session_id, sid):
        raise HTTPException(404, "Misi tidak ditemukan untuk sesi ini.")
    return row


def event(db: Session, row: PilotMission, kind: str) -> None:
    key = hashlib.sha256(f"{row.mission_id}:{kind}:{row.revision}".encode()).hexdigest()
    if db.get(PilotEvent, key) is None:
        db.add(PilotEvent(event_id=key, mission_id=row.mission_id, event_type=kind, revision=row.revision))
        db.flush()


def response(row: PilotMission) -> dict:
    return {"mission_id": row.mission_id, "revision": row.revision, "basket": row.snapshot, "mission": row.payload, "source": row.source}


@router.get("/config")
def config() -> dict:
    return {"mode": "pilot" if enabled() else "demo", "merchant_id": merchant_id() if enabled() else None,
            "shipping": shipping(), "ttl_hours": int(os.getenv("RASA_CATALOG_TTL_HOURS", "24")), "handoff": "local_preview_only"}


@router.post("/catalog/import", dependencies=[Depends(require_admin)])
def catalog_import(payload: CatalogImport, db: Session = Depends(get_db)) -> dict:
    return import_catalog(db, payload)


@router.post("/missions")
def start(payload: MissionStart, x_session_id: str = Header(min_length=16, max_length=80), db: Session = Depends(get_db)) -> dict:
    previous = db.get(PilotMission, payload.mission_id)
    if previous:
        row = owner(db, payload.mission_id, x_session_id)
        if row.payload != payload.mission.to_domain(payload.preferences).to_dict():
            raise HTTPException(409, "ID misi telah digunakan untuk input berbeda.")
        return response(row)
    mission = payload.mission.to_domain(payload.preferences)
    if set(mission.required_categories) & set(mission.optional_categories):
        raise HTTPException(422, "Kategori wajib dan opsional tidak boleh tumpang tindih.")
    known = set(db.scalars(select(Category.category_id)))
    if set(mission.all_categories) - known:
        raise HTTPException(422, "Kategori tidak dikenal.")
    basket = snapshot(db, mission)
    row = PilotMission(mission_id=payload.mission_id, session_id=x_session_id, source=basket["source"], payload=mission.to_dict(), snapshot=basket)
    db.add(row)
    db.flush()
    event(db, row, "mission_created")
    event(db, row, "basket_ready" if basket["feasible"] else "mission_infeasible")
    return response(row)


@router.post("/missions/{mid}/{action}")
def act(mid: str, action: str, payload: BasketAction, x_session_id: str = Header(min_length=16, max_length=80), db: Session = Depends(get_db)) -> dict:
    if action not in {"replace", "accept", "handoff"}:
        raise HTTPException(404, "Aksi tidak dikenal.")
    row = owner(db, mid, x_session_id)
    if payload.revision != row.revision:
        raise HTTPException(409, "Keranjang telah berubah; muat ulang hasil sebelum melanjutkan.")
    ids = [i["product_id"] for i in row.snapshot["items"]]
    if not ids:
        raise HTTPException(409, "Belum ada keranjang layak untuk diterima.")
    if action == "replace":
        if payload.product_id not in ids or not payload.replacement_id or payload.replacement_id in ids:
            raise HTTPException(422, "Pilih barang lama dan pengganti yang berbeda.")
        old = next(i for i in row.snapshot["items"] if i["product_id"] == payload.product_id)
        new = db.get(Product, payload.replacement_id)
        if not new or new.category_id != old["category_id"]:
            raise HTTPException(422, "Pengganti harus dari kategori yang sama.")
        ids[ids.index(payload.product_id)] = payload.replacement_id
    fresh = snapshot(db, Mission.from_dict(row.payload), ids)
    if fresh["source"] != row.source:
        raise HTTPException(409, "Jenis data katalog berubah; susun misi baru.")
    if not fresh["feasible"]:
        raise HTTPException(409, {"message": "Stok, harga, atau batas keranjang berubah. Susun ulang paket.", "basket": fresh})
    old_prices = {i["product_id"]: i["price"] for i in row.snapshot["items"]}
    changed = any(i["product_id"] in old_prices and old_prices[i["product_id"]] != i["price"] for i in fresh["items"])
    # Price changes require explicit review even if the basket still fits.
    old_costs = row.snapshot.get("costs", {})
    if changed or fresh["costs"]["shipping"] != old_costs.get("shipping"):
        raise HTTPException(409, "Harga atau biaya berubah. Susun ulang dan periksa paket sebelum menerima.")
    if action == "replace":
        row.snapshot = fresh
        try:
            db.flush()  # optimistic revision check
        except StaleDataError as exc:
            raise HTTPException(409, "Keranjang berubah di permintaan lain.") from exc
        event(db, row, "item_replaced")
    elif action == "accept":
        event(db, row, "basket_accepted")
    else:
        accepted = db.scalar(select(PilotEvent).where(PilotEvent.mission_id == mid, PilotEvent.event_type == "basket_accepted", PilotEvent.revision == row.revision))
        if not accepted:
            raise HTTPException(409, "Terima versi keranjang ini sebelum membuat ringkasan.")
        event(db, row, "handoff_prepared")
    result = response(row)
    if action == "handoff":
        label = os.getenv("RASA_HANDOFF_LABEL", "Proses pemesanan merchant (manual)")
        result["handoff"] = {"destination_label": label, "sent": False,
                             "text": label + "\n" + "\n".join(f"1 x {i['product_name']} ({i['product_id']}) Rp{i['price']:,.0f}" for i in fresh["items"]) + f"\nSubtotal Rp{fresh['total_price']:,.0f}\n" + fresh["costs"]["notice"]}
    return result


@router.get("/missions/{mid}")
def restore(mid: str, x_session_id: str = Header(min_length=16, max_length=80), db: Session = Depends(get_db)) -> dict:
    return response(owner(db, mid, x_session_id))


@router.get("/analytics", dependencies=[Depends(require_admin)])
def analytics(source: str = "pilot", db: Session = Depends(get_db)) -> dict:
    if source not in {"demo", "test", "pilot"}:
        raise HTTPException(422, "Source harus demo, test, atau pilot.")
    missions = list(db.scalars(select(PilotMission).where(PilotMission.source == source)))
    events = list(db.scalars(select(PilotEvent).join(PilotMission).where(PilotMission.source == source)))
    by_kind = {}
    for e in events:
        by_kind.setdefault(e.event_type, set()).add(e.mission_id)
    n = len(missions)
    accepted = by_kind.get("basket_accepted", set())
    ready = by_kind.get("basket_ready", set())
    times = []
    for m in missions:
        first = min((e.created_at for e in events if e.mission_id == m.mission_id and e.event_type == "basket_accepted"), default=None)
        if first:
            times.append((first - m.created_at).total_seconds())
    def rate(kind):
        return len(by_kind.get(kind, set())) / n if n else None
    return {"source": source, "denominators": {"created_missions": n, "feasible_missions": len(ready), "accepted_missions": len(accepted)},
            "mission_completion_rate": rate("basket_accepted"), "infeasible_rate": rate("mission_infeasible"),
            "basket_acceptance_among_feasible": len(accepted) / len(ready) if ready else None,
            "handoff_prepared_rate": rate("handoff_prepared"),
            "replacement_events_per_mission": sum(e.event_type == "item_replaced" for e in events) / n if n else None,
            "mean_seconds_to_accept_among_accepted": sum(times) / len(times) if times else None,
            "mean_required_coverage_latest": sum(m.snapshot["required_category_coverage"] for m in missions) / n if n else None,
            "confirmed_orders": None, "revenue": None, "margin": None, "returns": None,
            "notice": "Penerimaan adalah aksi UI; handoff_prepared hanya ringkasan lokal. Belum ada pesanan atau pendapatan terkonfirmasi."}
