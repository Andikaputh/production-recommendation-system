"""Katalog produk: caching in-memory, pencarian, dan detail produk."""

from __future__ import annotations

import json
from threading import RLock
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from rasa.data.schema import DatasetBundle
from rasa.db.models import Category, Merchant, Product
from rasa.utils import read_json

ATTRIBUTE_COLUMNS = ("style", "color", "material", "exclusive_group")


class CatalogService:
    def __init__(self) -> None:
        self.catalog: pd.DataFrame = pd.DataFrame()
        self.categories: pd.DataFrame = pd.DataFrame()
        self.merchants: pd.DataFrame = pd.DataFrame()
        self.dataset_version: str = "unknown"
        self._lock = RLock()

    @property
    def loaded(self) -> bool:
        return not self.catalog.empty

    def _enrich(self, products: pd.DataFrame, merchants: pd.DataFrame, categories: pd.DataFrame) -> pd.DataFrame:
        catalog = products.copy()
        catalog["category_name"] = catalog["category_id"].map(
            dict(zip(categories["category_id"], categories["category_name"], strict=False))
        )
        catalog["merchant_name"] = catalog["merchant_id"].map(
            dict(zip(merchants["merchant_id"], merchants["merchant_name"], strict=False))
        )
        catalog["merchant_rating"] = catalog["merchant_id"].map(
            dict(zip(merchants["merchant_id"], merchants["rating"], strict=False))
        ).astype(float)
        catalog["is_low_history_merchant"] = catalog["merchant_id"].map(
            dict(zip(merchants["merchant_id"], merchants["is_low_history"], strict=False))
        ).fillna(False).astype(bool)

        attributes = catalog["attributes"].map(
            lambda value: json.loads(value) if isinstance(value, str) else (value or {})
        )
        for column in ATTRIBUTE_COLUMNS:
            catalog[column] = attributes.map(
                lambda value, key=column: value.get(key, "") or ""
            )
        catalog["tags"] = attributes.map(lambda value: value.get("tags", []))
        catalog["eco_friendly"] = attributes.map(lambda value: bool(value.get("eco_friendly", False)))
        catalog["warranty_months"] = attributes.map(lambda value: int(value.get("warranty_months", 0)))
        catalog["attributes_json"] = attributes.map(lambda value: json.dumps(value, ensure_ascii=False))
        catalog["price"] = catalog["price"].astype(float)
        catalog["rating"] = catalog["rating"].astype(float)
        catalog["review_count"] = catalog["review_count"].fillna(0).astype(int)
        return catalog

    def load(self, session: Session) -> CatalogService:
        products = pd.DataFrame(
            [
                {
                    "product_id": row.product_id,
                    "product_name": row.product_name,
                    "category_id": row.category_id,
                    "subcategory": row.subcategory,
                    "description": row.description,
                    "brand": row.brand,
                    "price": float(row.price),
                    "rating": float(row.rating),
                    "review_count": int(row.review_count or 0),
                    "availability_status": row.availability_status,
                    "merchant_id": row.merchant_id,
                    "attributes": row.attributes or {},
                    "created_at": row.created_at,
                }
                for row in session.scalars(select(Product))
            ]
        )
        if products.empty:
            raise RuntimeError("Katalog database kosong. Jalankan `python scripts/seed_db.py`.")
        merchants = pd.DataFrame(
            [
                {
                    "merchant_id": row.merchant_id,
                    "merchant_name": row.merchant_name,
                    "rating": float(row.rating),
                    "is_low_history": bool(row.is_low_history),
                }
                for row in session.scalars(select(Merchant))
            ]
        )
        categories = pd.DataFrame(
            [
                {
                    "category_id": row.category_id,
                    "category_name": row.category_name,
                    "description": row.description,
                    "subcategories": row.subcategories or [],
                }
                for row in session.scalars(select(Category))
            ]
        )
        enriched = self._enrich(products, merchants, categories)
        with self._lock:
            self.catalog = enriched
            self.merchants = merchants
            self.categories = categories
            self.dataset_version = read_json(
                self.catalog_meta_path, {}
            ).get("dataset_version", "unknown")
        return self

    def load_from_bundle(self, bundle: DatasetBundle) -> CatalogService:
        enriched = self._enrich(bundle.catalog, bundle.merchants, bundle.categories)
        with self._lock:
            self.catalog = enriched
            self.merchants = bundle.merchants.copy()
            self.categories = bundle.categories.copy()
            self.dataset_version = bundle.summary.get("dataset_version", "unknown")
        return self

    @property
    def catalog_meta_path(self):
        from rasa.config import settings

        return settings.processed_dir / "catalog_meta.json"

    # ------------------------------------------------------------------
    def categories_payload(self) -> list[dict[str, Any]]:
        counts = self.catalog.groupby("category_id").size().to_dict()
        available = (
            self.catalog[self.catalog["availability_status"] == "available"]
            .groupby("category_id").size().to_dict()
        )
        payload = []
        for row in self.categories.to_dict("records"):
            payload.append({
                "category_id": row["category_id"],
                "category_name": row["category_name"],
                "description": row.get("description"),
                "subcategories": row.get("subcategories", []),
                "product_count": int(counts.get(row["category_id"], 0)),
                "available_count": int(available.get(row["category_id"], 0)),
            })
        return payload

    def get_product(self, product_id: str) -> dict[str, Any] | None:
        subset = self.catalog[self.catalog["product_id"] == product_id]
        if subset.empty:
            return None
        return self._product_payload(subset.iloc[0])

    def _product_payload(self, row: pd.Series) -> dict[str, Any]:
        return {
            "product_id": str(row["product_id"]),
            "product_name": str(row["product_name"]),
            "category_id": str(row["category_id"]),
            "category_name": str(row.get("category_name", row["category_id"])),
            "subcategory": str(row.get("subcategory", "")),
            "description": str(row["description"]),
            "brand": str(row["brand"]),
            "price": float(row["price"]),
            "rating": float(row["rating"]),
            "review_count": int(row.get("review_count", 0)),
            "availability_status": str(row["availability_status"]),
            "merchant_id": str(row["merchant_id"]),
            "merchant_name": str(row.get("merchant_name", row["merchant_id"])),
            "merchant_rating": float(row.get("merchant_rating", 0.0) or 0.0),
            "style": str(row.get("style", "")),
            "color": str(row.get("color", "")),
            "material": str(row.get("material", "")),
            "attributes": json.loads(row["attributes_json"]) if isinstance(row.get("attributes_json"), str) else {},
            "created_at": str(row.get("created_at", "")),
            "synthetic": True,
        }

    def search_products(
        self,
        *,
        query: str | None = None,
        category_ids: list[str] | None = None,
        merchant_id: str | None = None,
        min_rating: float | None = None,
        max_price: float | None = None,
        min_price: float | None = None,
        availability: str | None = None,
        sort_by: str = "rating",
        limit: int = 20,
        offset: int = 0,
    ) -> dict[str, Any]:
        frame = self.catalog
        if category_ids:
            frame = frame[frame["category_id"].isin(category_ids)]
        if merchant_id:
            frame = frame[frame["merchant_id"] == merchant_id]
        if min_rating is not None:
            frame = frame[frame["rating"] >= min_rating]
        if max_price is not None:
            frame = frame[frame["price"] <= max_price]
        if min_price is not None:
            frame = frame[frame["price"] >= min_price]
        if availability:
            frame = frame[frame["availability_status"] == availability]
        if query:
            needle = query.strip().lower()
            haystack = (
                frame["product_name"].str.lower() + " " + frame["description"].str.lower() + " "
                + frame["brand"].str.lower() + " " + frame["category_name"].str.lower()
            )
            frame = frame[haystack.str.contains(needle, regex=False, na=False)]

        sort_map = {
            "rating": ["rating", "review_count"],
            "price_asc": ["price"],
            "price_desc": ["price"],
            "newest": ["created_at"],
        }
        columns = sort_map.get(sort_by, ["rating", "review_count"])
        ascending = sort_by == "price_asc"
        frame = frame.sort_values(columns, ascending=ascending)

        total = int(len(frame))
        page = frame.iloc[offset: offset + limit]
        return {
            "total": total,
            "limit": limit,
            "offset": offset,
            "items": [self._product_payload(row) for _, row in page.iterrows()],
            "note": "Katalog, harga, dan stok adalah data simulasi.",
        }

    def merchants_payload(self) -> list[dict[str, Any]]:
        counts = self.catalog.groupby("merchant_id").size().to_dict()
        return [
            {
                "merchant_id": row["merchant_id"],
                "merchant_name": row["merchant_name"],
                "city": row.get("city"),
                "rating": float(row["rating"]),
                "is_low_history": bool(row["is_low_history"]),
                "product_count": int(counts.get(row["merchant_id"], 0)),
            }
            for row in self.merchants.to_dict("records")
        ]


catalog_service = CatalogService()
