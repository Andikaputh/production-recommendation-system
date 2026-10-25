"""Data-quality checks required by PRD sections 9.3 and 9.4."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from rasa.config import settings
from rasa.data.generate import CATEGORY_SPECS
from rasa.data.schema import POSITIVE_EVENTS, DatasetBundle, load_processed_dataset, temporal_split
from rasa.utils import iso_now, read_json, write_json

VALID_AVAILABILITY = {"available", "unavailable", "unknown"}
VALID_EVENT_TYPES = {"impression", "click", "save", "add_to_list", "purchase_proxy", "dismiss"}


def _result(name: str, status: str, severity: str, details: dict[str, Any], note: str = "") -> dict:
    return {
        "check": name,
        "status": status,
        "severity": severity,
        "details": details,
        "note": note,
    }


def run_data_quality_checks(bundle: DatasetBundle | None = None) -> dict:
    bundle = bundle or load_processed_dataset()
    catalog = bundle.catalog
    interactions = bundle.interactions
    merchants = bundle.merchants
    categories = bundle.categories
    users = bundle.users
    checks: list[dict] = []

    # 1. Duplikasi primary key
    for name, frame, column in (
        ("products", catalog, "product_id"),
        ("merchants", merchants, "merchant_id"),
        ("categories", categories, "category_id"),
        ("users", users, "user_id"),
        ("interactions", interactions, "event_id"),
    ):
        duplicates = int(frame[column].duplicated().sum())
        checks.append(_result(
            f"primary_key_duplicates:{name}",
            "pass" if duplicates == 0 else "fail",
            "critical",
            {"duplicates": duplicates, "rows": int(len(frame))},
        ))

    # 2. Valid prices
    invalid_price = int((catalog["price"] <= 0).sum())
    extreme_price = int((catalog["price"] > 10_000_000).sum())
    checks.append(_result(
        "price_validity",
        "pass" if invalid_price == 0 and extreme_price == 0 else "fail",
        "critical",
        {"non_positive": invalid_price, "above_10m": extreme_price,
         "min": int(catalog["price"].min()), "max": int(catalog["price"].max())},
    ))

    # 3. Missing values in required columns
    required = ["product_id", "product_name", "category_id", "price", "merchant_id", "availability_status"]
    missing_counts = {column: int(catalog[column].isna().sum()) for column in required}
    total_missing = sum(missing_counts.values())
    checks.append(_result(
        "required_missing_values",
        "pass" if total_missing == 0 else "fail",
        "critical",
        {"missing_counts": missing_counts},
    ))

    # 4. Unknown categories
    known_categories = set(categories["category_id"])
    unknown_categories = sorted(set(catalog["category_id"]) - known_categories)
    checks.append(_result(
        "unknown_categories",
        "pass" if not unknown_categories else "fail",
        "critical",
        {"unknown": unknown_categories, "known": sorted(known_categories)},
    ))

    # 5. Referential integrity from products to merchants and categories
    unknown_merchants = sorted(set(catalog["merchant_id"]) - set(merchants["merchant_id"]))
    checks.append(_result(
        "referential_integrity:product_merchant",
        "pass" if not unknown_merchants else "fail",
        "critical",
        {"unknown_merchant_ids": unknown_merchants},
    ))
    checks.append(_result(
        "referential_integrity:interaction_product",
        "pass" if set(interactions["product_id"]).issubset(set(catalog["product_id"])) else "fail",
        "critical",
        {"orphan_events": int((~interactions["product_id"].isin(catalog["product_id"])).sum())},
    ))

    # 6. Timestamps and chronological order
    timestamps = pd.to_datetime(interactions["event_timestamp"])
    null_timestamps = int(timestamps.isna().sum())
    future_events = int((timestamps > pd.Timestamp(settings.dataset.anchor_date).tz_localize(None)).sum())
    checks.append(_result(
        "timestamp_validity",
        "pass" if null_timestamps == 0 and future_events == 0 else "fail",
        "critical",
        {"null_timestamps": null_timestamps, "future_events": future_events,
         "min": str(timestamps.min()), "max": str(timestamps.max())},
    ))

    # 7. Duplicate interactions by user, product, type, and timestamp
    duplicate_interactions = int(
        interactions.duplicated(subset=["user_id", "product_id", "event_type", "event_timestamp"]).sum()
    )
    checks.append(_result(
        "duplicate_interactions",
        "pass" if duplicate_interactions == 0 else "warn",
        "warning",
        {"duplicates": duplicate_interactions},
        note="Duplicate interactions at identical timestamps may indicate duplicate events.",
    ))

    # 8. Distribusi user-item
    positives = interactions[interactions["event_type"].isin(POSITIVE_EVENTS)]
    per_user = positives.groupby("user_id").size()
    per_item = positives.groupby("product_id").size()
    sparsity = 1.0 - len(positives) / max(1, positives["user_id"].nunique() * catalog["product_id"].nunique())
    checks.append(_result(
        "user_item_distribution",
        "pass" if per_user.min() >= 1 and per_item.min() >= 1 else "warn",
        "warning",
        {
            "n_users_with_positives": int(per_user.size),
            "n_items_with_positives": int(per_item.size),
            "interactions_per_user": {
                "min": int(per_user.min()), "median": float(per_user.median()), "max": int(per_user.max())
            },
            "interactions_per_item": {
                "min": int(per_item.min()), "median": float(per_item.median()), "max": int(per_item.max())
            },
            "matrix_sparsity": round(float(sparsity), 4),
        },
    ))

    # 9. Temporal leakage: maximum train timestamp <= minimum test timestamp per user
    train, validation, test = bundle.train, bundle.validation, bundle.test
    leakage_users = 0
    for user_id, test_group in test.groupby("user_id"):
        train_group = train[train["user_id"] == user_id]
        if len(train_group) and train_group["event_timestamp"].max() > test_group["event_timestamp"].min():
            leakage_users += 1
    checks.append(_result(
        "temporal_leakage",
        "pass" if leakage_users == 0 else "fail",
        "critical",
        {"users_with_leakage": leakage_users, "n_test_users": int(test["user_id"].nunique())},
        note="Future interactions must not precede the same user's training data.",
    ))

    # 10. Isolasi train/test
    overlap = set(train["event_id"]) & set(test["event_id"])
    checks.append(_result(
        "train_test_isolation",
        "pass" if not overlap else "fail",
        "critical",
        {"overlapping_event_ids": len(overlap), "train_rows": int(len(train)), "test_rows": int(len(test))},
    ))

    # 11. Enum ketersediaan & event
    invalid_availability = sorted(set(catalog["availability_status"]) - VALID_AVAILABILITY)
    invalid_events = sorted(set(interactions["event_type"]) - VALID_EVENT_TYPES)
    checks.append(_result(
        "enum_validity",
        "pass" if not invalid_availability and not invalid_events else "fail",
        "critical",
        {"invalid_availability": invalid_availability, "invalid_event_types": invalid_events},
    ))

    # 12. Required-category coverage for demo scenarios
    counts = catalog[catalog["availability_status"] == "available"].groupby("category_id").size()
    missing_available = [spec.category_id for spec in CATEGORY_SPECS if counts.get(spec.category_id, 0) == 0]
    checks.append(_result(
        "available_products_per_category",
        "pass" if not missing_available else "fail",
        "critical",
        {"missing_available_categories": missing_available,
         "min_available_per_category": int(counts.min()) if len(counts) else 0},
    ))

    # 13. Schema-drift check against the manifest
    manifest = read_json(settings.raw_dir / "dataset_manifest.json", {})
    manifest_products = manifest.get("n_products")
    checks.append(_result(
        "schema_manifest_consistency",
        "pass" if manifest_products == len(catalog) else "warn",
        "warning",
        {"manifest_n_products": manifest_products, "actual_n_products": int(len(catalog)),
         "dataset_version": manifest.get("dataset_version")},
    ))

    critical_failures = [check for check in checks if check["status"] == "fail" and check["severity"] == "critical"]
    warnings = [check for check in checks if check["status"] == "warn"]
    report = {
        "generated_at": iso_now(),
        "dataset_version": settings.dataset.version,
        "summary": {
            "total_checks": len(checks),
            "passed": sum(1 for check in checks if check["status"] == "pass"),
            "warnings": len(warnings),
            "critical_failures": len(critical_failures),
            "passed_all_critical": len(critical_failures) == 0,
        },
        "checks": checks,
        "limitations": [
            "The dataset is entirely synthetic and does not represent a real marketplace.",
            "Prices and inventory are not real-time.",
            "Relevance labels come from simulated interactions, not real user preferences.",
        ],
    }
    return report


def render_markdown(report: dict) -> str:
    lines = [
        "# Data Quality Report",
        "",
        f"- Dataset: `{report['dataset_version']}`",
        f"- Generated: {report['generated_at']}",
        f"- Total pemeriksaan: {report['summary']['total_checks']}",
        f"- Lulus: {report['summary']['passed']}",
        f"- Warnings: {report['summary']['warnings']}",
        f"- Critical failures: {report['summary']['critical_failures']}",
        "",
        "| Pemeriksaan | Status | Severity | Detail |",
        "| --- | --- | --- | --- |",
    ]
    for check in report["checks"]:
        detail = ", ".join(f"{key}={value}" for key, value in check["details"].items())
        detail = detail.replace("|", "/")
        lines.append(f"| `{check['check']}` | {check['status']} | {check['severity']} | {detail} |")
    lines.extend(["", "## Limitations", ""])
    lines.extend(f"- {item}" for item in report["limitations"])
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    bundle = load_processed_dataset()
    # Ensure active splits match the latest configuration.
    if len(bundle.validation) == 0:
        train, validation, test = temporal_split(bundle.interactions)
        bundle.train, bundle.validation, bundle.test = train, validation, test
    report = run_data_quality_checks(bundle)
    write_json(settings.reports_dir / "data_quality.json", report)
    docs_dir = settings.root_dir / "docs" / "dataset"
    docs_dir.mkdir(parents=True, exist_ok=True)
    (docs_dir / "data-quality-report.md").write_text(render_markdown(report), encoding="utf-8")
    print(f"Data quality: {report['summary']}")


if __name__ == "__main__":
    main()
