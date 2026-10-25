"""Pemuatan data, validasi skema, dan pemisahan temporal anti-leakage."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from rasa.config import settings
from rasa.utils import read_json, write_json

POSITIVE_EVENTS = ("click", "save", "add_to_list", "purchase_proxy")
CATALOG_COLUMNS = (
    "product_id", "product_name", "category_id", "category_name", "subcategory",
    "description", "brand", "price", "rating", "review_count", "availability_status",
    "merchant_id", "attributes", "created_at",
)
INTERACTION_COLUMNS = (
    "event_id", "session_id", "user_id", "product_id", "event_type",
    "event_timestamp", "experiment_variant", "source",
)


class DataValidationError(ValueError):
    """Dilempar ketika dataset tidak memenuhi skema minimum."""


@dataclass
class DatasetBundle:
    categories: pd.DataFrame
    merchants: pd.DataFrame
    catalog: pd.DataFrame
    users: pd.DataFrame
    interactions: pd.DataFrame
    train: pd.DataFrame
    validation: pd.DataFrame
    test: pd.DataFrame
    summary: dict

    @property
    def available_catalog(self) -> pd.DataFrame:
        return self.catalog[self.catalog["availability_status"] == "available"].copy()


def _parse_attributes(catalog: pd.DataFrame) -> pd.DataFrame:
    catalog = catalog.copy()
    parsed = catalog["attributes"].map(lambda value: json.loads(value) if isinstance(value, str) else (value or {}))
    catalog["style"] = parsed.map(lambda value: value.get("style", ""))
    catalog["color"] = parsed.map(lambda value: value.get("color", ""))
    catalog["material"] = parsed.map(lambda value: value.get("material", ""))
    catalog["eco_friendly"] = parsed.map(lambda value: bool(value.get("eco_friendly", False)))
    catalog["warranty_months"] = parsed.map(lambda value: int(value.get("warranty_months", 0)))
    catalog["exclusive_group"] = parsed.map(lambda value: value.get("exclusive_group") or "")
    catalog["tags"] = parsed.map(lambda value: value.get("tags", []))
    catalog["attributes_json"] = catalog["attributes"]
    return catalog


def load_raw_dataset(raw_dir: Path | None = None) -> tuple[pd.DataFrame, ...]:
    raw_dir = raw_dir or settings.raw_dir
    required = ["categories.csv", "merchants.csv", "products.csv", "users.csv", "interactions.csv"]
    missing = [name for name in required if not (raw_dir / name).exists()]
    if missing:
        raise FileNotFoundError(
            f"Dataset mentah belum lengkap: {missing}. Jalankan `make data` atau "
            "`python scripts/generate_data.py`."
        )
    categories = pd.read_csv(raw_dir / "categories.csv")
    merchants = pd.read_csv(raw_dir / "merchants.csv")
    catalog = pd.read_csv(raw_dir / "products.csv")
    users = pd.read_csv(raw_dir / "users.csv")
    interactions = pd.read_csv(raw_dir / "interactions.csv")

    missing_columns = [column for column in CATALOG_COLUMNS if column not in catalog.columns]
    if missing_columns:
        raise DataValidationError(f"Kolom katalog hilang: {missing_columns}")
    interaction_missing = [column for column in INTERACTION_COLUMNS if column not in interactions.columns]
    if interaction_missing:
        raise DataValidationError(f"Kolom interaksi hilang: {interaction_missing}")

    catalog = _parse_attributes(catalog)
    interactions["event_timestamp"] = pd.to_datetime(interactions["event_timestamp"], utc=True).dt.tz_localize(None)
    catalog["created_at"] = pd.to_datetime(catalog["created_at"], utc=True).dt.tz_localize(None)
    categories["subcategories"] = categories["subcategories"].map(
        lambda value: json.loads(value) if isinstance(value, str) else []
    )
    for column in ("preferred_categories", "preferred_brands", "preferred_styles", "preferred_colors"):
        users[column] = users[column].map(
            lambda value: json.loads(value) if isinstance(value, str) else (value or [])
        )
    return categories, merchants, catalog, users, interactions


def temporal_split(
    interactions: pd.DataFrame,
    test_fraction: float | None = None,
    validation_fraction: float | None = None,
    min_train_positives: int | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Split temporal per pengguna berbasis event positif.

    Semua event positif diurutkan berdasarkan waktu. ``test_fraction`` terakhir
    menjadi holdout, lalu ``validation_fraction`` dari sisa data menjadi
    validation. Event non-positif (impression) tidak dipakai untuk evaluasi
    ranking agar label relevansi tetap eksplisit.
    """
    test_fraction = settings.get("split.test_fraction", 0.2) if test_fraction is None else test_fraction
    validation_fraction = (
        settings.get("split.validation_fraction", 0.15) if validation_fraction is None else validation_fraction
    )
    min_train = settings.get("split.min_train_positives", 3) if min_train_positives is None else min_train_positives

    positives = interactions[interactions["event_type"].isin(POSITIVE_EVENTS)].copy()
    positives = positives.sort_values(["user_id", "event_timestamp", "event_id"]).reset_index(drop=True)

    train_parts, validation_parts, test_parts = [], [], []
    for _, group in positives.groupby("user_id", sort=False):
        n = len(group)
        if n <= min_train:
            # Pengguna dengan histori sangat sedikit tetap masuk train; mereka
            # diukur terpisah sebagai kelompok cold-start.
            train_parts.append(group)
            continue
        n_test = max(1, int(round(n * test_fraction)))
        n_validation = max(0, int(round((n - n_test) * validation_fraction)))
        n_validation = min(n_validation, max(0, n - n_test - min_train))
        split_test = n - n_test
        split_validation = split_test - n_validation
        train_parts.append(group.iloc[:split_validation])
        validation_parts.append(group.iloc[split_validation:split_test])
        test_parts.append(group.iloc[split_test:])

    train = pd.concat(train_parts, ignore_index=True) if train_parts else positives.iloc[0:0].copy()
    validation = (
        pd.concat(validation_parts, ignore_index=True) if validation_parts else positives.iloc[0:0].copy()
    )
    test = pd.concat(test_parts, ignore_index=True) if test_parts else positives.iloc[0:0].copy()

    # Event non-positif (impresi/dismiss) tidak dipakai untuk membangun fitur
    # maupun evaluasi ranking. Menyimpannya di ``train`` akan menciptakan ilusi
    # kebocoran temporal karena impresi dibuat mengelilingi event positif,
    # termasuk holdout. Dataset mentah tetap menyimpan seluruh event untuk
    # analitik dan audit.
    return train, validation, test


def build_dataset(write: bool = True) -> DatasetBundle:
    categories, merchants, catalog, users, interactions = load_raw_dataset()

    train, validation, test = temporal_split(interactions)
    processed_dir = settings.processed_dir
    processed_dir.mkdir(parents=True, exist_ok=True)

    summary = {
        "dataset_version": settings.dataset.version,
        "synthetic": True,
        "n_categories": int(len(categories)),
        "n_merchants": int(len(merchants)),
        "n_products": int(len(catalog)),
        "n_users": int(len(users)),
        "n_events": int(len(interactions)),
        "n_train": int(len(train)),
        "n_validation": int(len(validation)),
        "n_test": int(len(test)),
        "n_train_users": int(train["user_id"].nunique()),
        "n_test_users": int(test["user_id"].nunique()),
        "n_cold_start_users": int(users["is_cold_start"].sum()),
        "test_fraction": settings.get("split.test_fraction", 0.2),
        "validation_fraction": settings.get("split.validation_fraction", 0.15),
        "min_train_positives": settings.get("split.min_train_positives", 3),
        "positive_event_types": list(POSITIVE_EVENTS),
        "availability_counts": catalog["availability_status"].value_counts().to_dict(),
        "price_stats": {
            "min": int(catalog["price"].min()),
            "median": int(catalog["price"].median()),
            "max": int(catalog["price"].max()),
        },
        "events_per_user": {
            "mean": round(float(interactions.groupby("user_id").size().mean()), 2),
            "median": float(interactions.groupby("user_id").size().median()),
        },
    }

    if write:
        catalog.to_csv(processed_dir / "catalog.csv", index=False, encoding="utf-8")
        train.to_csv(processed_dir / "interactions_train.csv", index=False, encoding="utf-8")
        validation.to_csv(processed_dir / "interactions_validation.csv", index=False, encoding="utf-8")
        test.to_csv(processed_dir / "interactions_test.csv", index=False, encoding="utf-8")
        users.to_csv(processed_dir / "users.csv", index=False, encoding="utf-8")
        write_json(processed_dir / "split_summary.json", summary)
        write_json(processed_dir / "catalog_meta.json", {
            "dataset_version": settings.dataset.version,
            "n_products": int(len(catalog)),
            "generated_at": read_json(settings.raw_dir / "dataset_manifest.json", {}).get("generated_at"),
            "note": "Katalog, harga, stok, dan merchant adalah data simulasi.",
        })

    return DatasetBundle(
        categories=categories,
        merchants=merchants,
        catalog=catalog,
        users=users,
        interactions=interactions,
        train=train,
        validation=validation,
        test=test,
        summary=summary,
    )


def load_processed_dataset() -> DatasetBundle:
    """Muat hasil build_dataset tanpa regenerasi."""
    processed_dir = settings.processed_dir
    required = ["catalog.csv", "interactions_train.csv", "interactions_test.csv", "users.csv"]
    missing = [name for name in required if not (processed_dir / name).exists()]
    if missing:
        raise FileNotFoundError(f"Data processed belum lengkap: {missing}. Jalankan `make data`.")
    categories, merchants, _, users, _ = load_raw_dataset()
    catalog = pd.read_csv(processed_dir / "catalog.csv")
    # Kolom atribut sudah diturunkan saat build; tetap pastikan tipe konsisten.
    catalog["created_at"] = pd.to_datetime(catalog["created_at"], utc=True).dt.tz_localize(None)
    train = pd.read_csv(processed_dir / "interactions_train.csv")
    validation_path = processed_dir / "interactions_validation.csv"
    validation = pd.read_csv(validation_path) if validation_path.exists() else train.iloc[0:0].copy()
    test = pd.read_csv(processed_dir / "interactions_test.csv")
    for frame in (train, validation, test):
        if len(frame):
            frame["event_timestamp"] = pd.to_datetime(frame["event_timestamp"], utc=True).dt.tz_localize(None)
    summary = read_json(processed_dir / "split_summary.json", {})
    return DatasetBundle(
        categories=categories,
        merchants=merchants,
        catalog=catalog,
        users=users,
        interactions=pd.concat([train, validation, test], ignore_index=True),
        train=train,
        validation=validation,
        test=test,
        summary=summary,
    )


def user_positive_catalog(events: pd.DataFrame) -> dict[str, set[str]]:
    positives = events[events["event_type"].isin(POSITIVE_EVENTS)]
    return positives.groupby("user_id")["product_id"].agg(set).to_dict()


def user_event_weights(events: pd.DataFrame) -> dict[str, dict[str, float]]:
    weights = settings.get("features.event_weights", {})
    positives = events[events["event_type"].isin(POSITIVE_EVENTS)]
    result: dict[str, dict[str, float]] = {}
    for user_id, group in positives.groupby("user_id"):
        scores: dict[str, float] = {}
        for row in group.itertuples():
            scores[row.product_id] = scores.get(row.product_id, 0.0) + float(weights.get(row.event_type, 1.0))
        result[user_id] = scores
    return result


def most_popular_categories(events: pd.DataFrame, catalog: pd.DataFrame, top_n: int = 4) -> dict[str, list[str]]:
    positives = events[events["event_type"].isin(POSITIVE_EVENTS)].merge(
        catalog[["product_id", "category_id"]], on="product_id", how="left"
    )
    result: dict[str, list[str]] = {}
    for user_id, group in positives.groupby("user_id"):
        counts = group.groupby("category_id").size().sort_values(ascending=False)
        result[user_id] = list(counts.head(top_n).index)
    return result


def dataset_fingerprint() -> str:
    manifest = read_json(settings.raw_dir / "dataset_manifest.json", {})
    return str(manifest.get("dataset_version", settings.dataset.version))


def popularity_table(events: pd.DataFrame, catalog: pd.DataFrame) -> pd.DataFrame:
    positives = events[events["event_type"].isin(POSITIVE_EVENTS)]
    counts = positives.groupby("product_id").size().rename("interaction_count")
    table = catalog[["product_id", "category_id", "price", "rating"]].merge(
        counts, left_on="product_id", right_index=True, how="left"
    )
    table["interaction_count"] = table["interaction_count"].fillna(0).astype(int)
    return table


def price_quantiles(catalog: pd.DataFrame) -> dict[str, dict[str, float]]:
    result: dict[str, dict[str, float]] = {}
    for category_id, group in catalog.groupby("category_id"):
        quantiles = np.quantile(group["price"].to_numpy(dtype=float), [0.0, 0.25, 0.5, 0.75, 1.0])
        result[category_id] = {
            "min": float(quantiles[0]),
            "q25": float(quantiles[1]),
            "median": float(quantiles[2]),
            "q75": float(quantiles[3]),
            "max": float(quantiles[4]),
        }
    return result
