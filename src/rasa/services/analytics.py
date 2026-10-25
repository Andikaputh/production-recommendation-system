"""Dashboard analytics: agregasi event demo, kualitas misi, dan eksposur katalog."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import timedelta
from typing import Any

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from rasa.config import settings
from rasa.db.models import (
    BasketSolution,
    InteractionEvent,
    ModelVersion,
    Product,
    RecommendationItem,
    RecommendationRequest,
)
from rasa.services.model_registry import registry
from rasa.utils import iso_now, read_json, utcnow


def _gini(values: list[float]) -> float:
    if not values:
        return 0.0
    array = np.sort(np.asarray(values, dtype=float))
    if array.sum() == 0:
        return 0.0
    n = len(array)
    index = np.arange(1, n + 1)
    return float((2 * np.sum(index * array) / (n * array.sum())) - (n + 1) / n)


def _percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    return float(np.percentile(np.asarray(values, dtype=float), p))


def _sample_warning(samples: int) -> str | None:
    minimum = int(settings.get("evaluation.min_sample_warning", 30))
    if samples < minimum:
        return (
            f"Sampel hanya {samples} (< {minimum}). Metrik ditampilkan sebagai indikasi awal, "
            "bukan kesimpulan statistik."
        )
    return None


def analytics_summary(
    session: Session,
    *,
    days: int = 30,
    model_version: str | None = None,
    strategy: str | None = None,
) -> dict[str, Any]:
    since = utcnow() - timedelta(days=max(1, min(days, 365)))
    request_query = select(RecommendationRequest).where(RecommendationRequest.created_at >= since)
    if model_version:
        request_query = request_query.where(RecommendationRequest.model_version == model_version)
    if strategy:
        request_query = request_query.where(RecommendationRequest.strategy == strategy)
    requests = list(session.scalars(request_query))

    request_ids = {row.request_id for row in requests}
    latencies = [float(row.latency_ms) for row in requests]
    status_counts = Counter(row.status for row in requests)
    model_counts = Counter(row.model_version for row in requests)
    strategy_counts = Counter(row.strategy for row in requests)

    by_day: dict[str, dict[str, Any]] = defaultdict(lambda: {"requests": 0, "latency_ms": []})
    for row in requests:
        day = row.created_at.date().isoformat() if row.created_at else "unknown"
        by_day[day]["requests"] += 1
        by_day[day]["latency_ms"].append(float(row.latency_ms))

    basket_query = select(BasketSolution).where(BasketSolution.created_at >= since)
    baskets = list(session.scalars(basket_query))
    if request_ids:
        baskets = [basket for basket in baskets if basket.request_id in request_ids]
    feasible_baskets = [basket for basket in baskets if basket.status == "feasible"]
    infeasible_baskets = [basket for basket in baskets if basket.status == "infeasible"]

    feedback_query = select(InteractionEvent).where(
        InteractionEvent.event_timestamp >= since,
        InteractionEvent.source != "synthetic_history",
    )
    events = list(session.scalars(feedback_query))
    event_counts = Counter(row.event_type for row in events)
    sessions_with_feedback = len({row.session_id for row in events})

    impressions = event_counts.get("impression", 0)
    clicks = event_counts.get("click", 0)
    saves = event_counts.get("save", 0)
    add_to_list = event_counts.get("add_to_list", 0)
    dismiss = event_counts.get("dismiss", 0)

    recommended_rows = []
    if request_ids:
        recommended_rows = list(session.scalars(
            select(RecommendationItem).where(RecommendationItem.request_id.in_(request_ids))
        ))
    exposure_counts = Counter(row.product_id for row in recommended_rows)
    products = {row.product_id: row for row in session.scalars(select(Product))}
    exposure_values = list(exposure_counts.values())
    gini = _gini(exposure_values)
    unique_exposed = len(exposure_counts)

    popularity_counts: dict[str, int] = {}
    if registry.popularity is not None:
        popularity_counts = registry.popularity.global_counts
    else:
        history = list(session.scalars(
            select(InteractionEvent).where(
                InteractionEvent.source == "synthetic_history",
                InteractionEvent.event_type.in_(("click", "save", "add_to_list", "purchase_proxy")),
            )
        ))
        popularity_counts = dict(Counter(row.product_id for row in history))
    catalog_counts = [popularity_counts.get(product_id, 0) for product_id in products]
    long_tail_threshold = float(np.median(catalog_counts)) if catalog_counts else 0.0
    exposed_product_ids = list(exposure_counts.keys())
    long_tail_share = (
        sum(1 for product_id in exposed_product_ids if popularity_counts.get(product_id, 0) <= long_tail_threshold)
        / len(exposed_product_ids)
        if exposed_product_ids else 0.0
    )
    new_item_share = (
        sum(1 for product_id in exposed_product_ids if popularity_counts.get(product_id, 0) == 0)
        / len(exposed_product_ids)
        if exposed_product_ids else 0.0
    )

    category_exposure = Counter()
    merchant_exposure = Counter()
    for product_id, count in exposure_counts.items():
        product = products.get(product_id)
        if product is None:
            continue
        category_exposure[product.category_id] += count
        merchant_exposure[product.merchant_id] += count

    feedback_by_type = {event: int(event_counts.get(event, 0)) for event in (
        "impression", "click", "save", "add_to_list", "purchase_proxy", "dismiss"
    )}
    offline = read_json(settings.reports_dir / "evaluation.json", {}) or {}

    sample_size = len(requests)
    warnings = [message for message in (_sample_warning(sample_size),) if message]
    if impressions and impressions < 30:
        warnings.append("CTR proxy dihitung dari < 30 impresi; jangan ditafsirkan sebagai dampak bisnis.")
    if not requests:
        warnings.append(
            "Belum ada request rekomendasi pada periode ini. Buka demo dan jalankan satu misi "
            "untuk mengisi metrik."
        )

    return {
        "generated_at": iso_now(),
        "period": {
            "days": days,
            "start": since.date().isoformat(),
            "end": utcnow().date().isoformat(),
        },
        "filters": {"model_version": model_version, "strategy": strategy},
        "data_source": {
            "type": "demo_events_and_offline_evaluation",
            "dataset_version": registry.dataset_version,
            "model_version": registry.model_version if registry.ready else None,
            "note": "Seluruh data katalog dan event demo bersifat simulasi.",
        },
        "sample_sizes": {
            "recommendation_requests": sample_size,
            "basket_solutions": len(baskets),
            "feedback_events": len(events),
            "sessions_with_feedback": sessions_with_feedback,
            "recommendation_items": len(recommended_rows),
        },
        "warnings": warnings,
        "recommendation_quality": {
            "offline_metrics": offline.get("ranking", {}),
            "offline_experiment_source": "artifacts/reports/evaluation.json",
            "catalog_coverage": round(unique_exposed / max(1, len(products)), 4),
            "distinct_products_exposed": unique_exposed,
            "exposure_concentration_gini": round(gini, 4),
        },
        "mission_quality": {
            "budget_feasibility_rate": round(len(feasible_baskets) / max(1, len(baskets)), 4),
            "infeasible_mission_rate": round(len(infeasible_baskets) / max(1, len(baskets)), 4),
            "avg_required_category_coverage": round(
                float(np.mean([basket.required_category_coverage for basket in baskets])) if baskets else 0.0, 4
            ),
            "avg_budget_utilization": round(
                float(np.mean([
                    (basket.total_price / max(1.0, (basket.total_price + basket.budget_remaining)))
                    for basket in baskets
                ])) if baskets else 0.0,
                4,
            ),
            "avg_merchant_count": round(
                float(np.mean([basket.merchant_count for basket in baskets])) if baskets else 0.0, 2
            ),
            "merchant_count_distribution": dict(Counter(basket.merchant_count for basket in baskets)),
            "solver_usage": dict(Counter(basket.solver for basket in baskets)),
            "infeasibility_explanation_rate": round(
                sum(
                    1 for basket in infeasible_baskets
                    if (basket.explanation or {}).get("suggestions")
                ) / max(1, len(infeasible_baskets)),
                4,
            ) if infeasible_baskets else None,
        },
        "product_exposure": {
            "long_tail_share": round(long_tail_share, 4),
            "long_tail_threshold_interactions": long_tail_threshold,
            "new_item_exposure_share": round(new_item_share, 4),
            "top_categories": category_exposure.most_common(5),
            "top_merchants": merchant_exposure.most_common(5),
            "gini": round(gini, 4),
        },
        "business_proxy": {
            "feedback_by_type": feedback_by_type,
            "click_through_proxy": round(clicks / impressions, 4) if impressions else None,
            "save_to_impression_rate": round(saves / impressions, 4) if impressions else None,
            "add_to_list_rate": round(add_to_list / impressions, 4) if impressions else None,
            "dismiss_rate": round(dismiss / impressions, 4) if impressions else None,
            "mission_completion_proxy": round(
                sum(1 for basket in feasible_baskets) / max(1, sample_size), 4
            ) if sample_size else None,
            "caveat": (
                "Metrik ini dihitung dari event demo/simulasi. Tidak boleh disebut conversion "
                "rate atau dampak revenue."
            ),
        },
        "system_health": {
            "api_latency_ms": {
                "p50": _percentile(latencies, 50),
                "p95": _percentile(latencies, 95),
                "p99": _percentile(latencies, 99),
            },
            "error_rate": round(
                (status_counts.get("error", 0) / sample_size) if sample_size else 0.0, 4
            ),
            "fallback_rate": round(
                (sum(1 for row in requests if row.fallback_used) / sample_size) if sample_size else 0.0, 4
            ),
            "request_volume": sample_size,
            "model_version_usage": dict(model_counts),
            "strategy_usage": dict(strategy_counts),
            "status_counts": dict(status_counts),
            "timeseries": [
                {
                    "date": day,
                    "requests": values["requests"],
                    "p95_latency_ms": _percentile(values["latency_ms"], 95),
                }
                for day, values in sorted(by_day.items())
            ],
        },
        "model_versions": [
            {
                "model_version": row.model_version,
                "trained_at": row.trained_at.isoformat(timespec="seconds") if row.trained_at else None,
                "dataset_version": row.dataset_version,
                "is_active": bool(row.is_active),
                "metrics": row.metrics,
            }
            for row in session.scalars(select(ModelVersion))
        ],
    }


def experiment_catalog(session: Session) -> dict[str, Any]:
    from rasa.utils import read_json

    experiments_path = settings.root_dir / "configs" / "experiments.yaml"
    import yaml

    config = yaml.safe_load(experiments_path.read_text(encoding="utf-8")) if experiments_path.exists() else {}
    results = read_json(settings.reports_dir / "experiments.json", {}) or {}
    return {
        "experiments": config.get("experiments", []),
        "ab_tests": config.get("ab_tests", []),
        "results": results,
        "note": (
            "Eksperimen offline dijalankan pada holdout temporal. Simulasi A/B bukan bukti kausal "
            "dan tidak boleh dilaporkan sebagai peningkatan production."
        ),
        "generated_at": iso_now(),
    }
