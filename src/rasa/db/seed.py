"""Seed database demo dari dataset sintetis dan artefak model.

Menjalankan ulang seed akan mengosongkan tabel (``drop=True``) agar data demo
selalu konsisten dengan dataset berversi. Harga/stok tetap data simulasi.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import yaml
from sqlalchemy import insert

from rasa.config import settings
from rasa.data.schema import DatasetBundle, load_processed_dataset
from rasa.db.models import (
    AnonymousSession,
    Category,
    ExperimentDefinition,
    InteractionEvent,
    Merchant,
    ModelVersion,
    Product,
    ProductAttribute,
    UserPreference,
)
from rasa.db.session import init_db, session_scope
from rasa.utils import read_json, short_hash

SCALAR_ATTRIBUTES = ("color", "style", "material", "use_case", "audience", "eco_friendly", "warranty_months")


def _chunks(rows: list[dict[str, Any]], size: int = 2000):
    for start in range(0, len(rows), size):
        yield rows[start : start + size]


def _product_rows(bundle: DatasetBundle) -> list[dict[str, Any]]:
    rows = []
    for record in bundle.catalog.to_dict("records"):
        attributes = record.get("attributes")
        if isinstance(attributes, str):
            import json

            attributes = json.loads(attributes)
        rows.append(
            {
                "product_id": record["product_id"],
                "product_name": record["product_name"],
                "category_id": record["category_id"],
                "subcategory": record.get("subcategory"),
                "description": record["description"],
                "brand": record["brand"],
                "price": float(record["price"]),
                "rating": float(record["rating"]),
                "review_count": int(record["review_count"]),
                "availability_status": record["availability_status"],
                "merchant_id": record["merchant_id"],
                "attributes": attributes or {},
                "created_at": pd.Timestamp(record["created_at"]).to_pydatetime(),
            }
        )
    return rows


def _attribute_rows(bundle: DatasetBundle) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for record in bundle.catalog.to_dict("records"):
        attributes = record.get("attributes")
        if isinstance(attributes, str):
            import json

            attributes = json.loads(attributes)
        for key in SCALAR_ATTRIBUTES:
            if key not in (attributes or {}):
                continue
            value = attributes[key]
            rows.append(
                {
                    "product_id": record["product_id"],
                    "attribute_key": key,
                    "attribute_value": str(value),
                }
            )
    return rows


def seed_database(drop: bool = True, include_events: bool = True) -> dict[str, int]:
    bundle = load_processed_dataset()
    init_db(drop=drop)

    counts: dict[str, int] = {}

    with session_scope() as session:
        categories = [
            {
                "category_id": row["category_id"],
                "category_name": row["category_name"],
                "description": row.get("description"),
                "subcategories": row.get("subcategories"),
            }
            for row in bundle.categories.to_dict("records")
        ]
        session.execute(insert(Category), categories)
        counts["categories"] = len(categories)

        merchants = [
            {
                "merchant_id": row["merchant_id"],
                "merchant_name": row["merchant_name"],
                "city": row.get("city"),
                "rating": float(row.get("rating", 4.3)),
                "is_low_history": bool(row.get("is_low_history", False)),
            }
            for row in bundle.merchants.to_dict("records")
        ]
        session.execute(insert(Merchant), merchants)
        counts["merchants"] = len(merchants)

        products = _product_rows(bundle)
        session.execute(insert(Product), products)
        counts["products"] = len(products)

        attributes = _attribute_rows(bundle)
        session.execute(insert(ProductAttribute), attributes)
        counts["product_attributes"] = len(attributes)

        preferences = []
        for row in bundle.users.to_dict("records"):
            preferences.append(
                {
                    "user_id": row["user_id"],
                    "preferred_categories": row.get("preferred_categories") or [],
                    "preferred_brands": row.get("preferred_brands") or [],
                    "preferred_styles": row.get("preferred_styles") or [],
                    "preferred_colors": row.get("preferred_colors") or [],
                    "preferred_price_range": {
                        "sensitivity": row.get("price_sensitivity", "sedang"),
                    },
                    "price_sensitivity": row.get("price_sensitivity"),
                }
            )
        session.execute(insert(UserPreference), preferences)
        counts["users"] = len(preferences)

        sessions = [
            {
                "session_id": f"seed-{user_id}",
                "experiment_variant": "organic",
                "user_agent_family": "synthetic",
            }
            for user_id in bundle.users["user_id"].head(50)
        ]
        session.execute(insert(AnonymousSession), sessions)
        counts["sessions"] = len(sessions)

        if include_events:
            events = []
            for record in bundle.interactions.to_dict("records"):
                events.append(
                    {
                        "event_id": record["event_id"],
                        "session_id": record["session_id"],
                        "user_id": record.get("user_id"),
                        "product_id": record["product_id"],
                        "event_type": record["event_type"],
                        "event_timestamp": pd.Timestamp(record["event_timestamp"]).to_pydatetime(),
                        "experiment_variant": record.get("experiment_variant"),
                        "source": record.get("source"),
                    }
                )
            for chunk in _chunks(events):
                session.execute(insert(InteractionEvent), chunk)
            counts["interaction_events"] = len(events)

        experiments: list[dict[str, Any]] = []
        experiments_path = settings.root_dir / "configs" / "experiments.yaml"
        if experiments_path.exists():
            payload = yaml.safe_load(experiments_path.read_text(encoding="utf-8")) or {}
            for item in payload.get("experiments", []):
                experiments.append(
                    {
                        "experiment_id": item["experiment_id"],
                        "name": item["name"],
                        "description": item.get("purpose"),
                        "model": item.get("model"),
                        "config": item,
                    }
                )
            for item in payload.get("ab_tests", []):
                experiments.append(
                    {
                        "experiment_id": item["experiment_id"],
                        "name": item["name"],
                        "description": item.get("description"),
                        "model": "ab_simulation",
                        "config": item,
                    }
                )
        session.execute(insert(ExperimentDefinition), experiments)
        counts["experiments"] = len(experiments)

        manifest = read_json(settings.models_dir / "feature_manifest.json", {}) or {}
        hybrid = read_json(settings.models_dir / "hybrid_config.json", {}) or {}
        evaluation = read_json(settings.reports_dir / "evaluation.json", {}) or {}
        if manifest:
            metrics = {
                "ranking": {
                    key: value.get("metrics")
                    for key, value in (evaluation.get("ranking") or {}).items()
                },
                "selected_weights": hybrid.get("weights"),
            }
            session.execute(
                insert(ModelVersion),
                [
                    {
                        "model_version": manifest.get("model_version", settings.model_version),
                        "dataset_version": manifest.get("dataset_version"),
                        "config_hash": short_hash(str(hybrid.get("weights", {})), str(manifest)),
                        "metrics": metrics,
                        "artifact_path": str(settings.models_dir),
                        "is_active": True,
                    }
                ],
            )
            counts["model_versions"] = 1

    return counts
