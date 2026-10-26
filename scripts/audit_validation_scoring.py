"""Validate cached grid scoring against real inference on validation, without retuning."""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from rasa.config import settings  # noqa: E402
from rasa.data.schema import POSITIVE_EVENTS, load_processed_dataset  # noqa: E402
from rasa.evaluation.ranking_metrics import aggregate_metrics, evaluate_recommendation  # noqa: E402
from rasa.evaluation.tuning import validation_order  # noqa: E402
from rasa.ranking.ranker import simulate_mission_for_user  # noqa: E402
from rasa.services.catalog import CatalogService  # noqa: E402
from rasa.services.model_registry import ModelRegistry  # noqa: E402
from rasa.utils import file_sha256, iso_now, write_json  # noqa: E402


def main():
    registry = ModelRegistry().load()
    if not registry.ready:
        raise SystemExit(registry.error)
    bundle = load_processed_dataset()
    catalog = CatalogService().load_from_bundle(bundle).catalog
    positive_train = bundle.train[bundle.train.event_type.isin(POSITIVE_EVENTS)]
    seen = positive_train.groupby("user_id").product_id.agg(set).to_dict()
    histories = {}
    for row in positive_train.itertuples():
        bucket = histories.setdefault(row.user_id, {})
        bucket[row.product_id] = bucket.get(row.product_id, 0) + settings.get("features.event_weights", {}).get(row.event_type, 1)
    relevant = {uid: set(group.product_id) - seen.get(uid, set()) for uid, group in bundle.validation[bundle.validation.event_type.isin(POSITIVE_EVENTS)].groupby("user_id")}
    relevant = {uid: items for uid, items in relevant.items() if items}
    users = bundle.users.set_index("user_id").to_dict("index")
    metrics, mismatches = [], []
    for uid in sorted(relevant)[:180]:
        mission = simulate_mission_for_user(pd.Series(users[uid]), catalog)
        mission_ids = set(catalog[catalog.category_id.isin(mission.all_categories)].product_id)
        labels = relevant[uid] & mission_ids
        if not labels:
            continue
        ranked = registry.ranker.rank(catalog, mission, user_id=uid, history_weights=histories.get(uid), strategy="hybrid_mission", top_k=10, exclude_product_ids=seen.get(uid, set()))
        actual = [item.product_id for item in ranked.items]
        predicted = validation_order(ranked.scored, registry.ranker.weights, ranked.diagnostics["cold_start"]["n_user_interactions"], int(registry.ranker.config.get("min_interactions", 3)), 10) if actual else []
        if actual != predicted:
            mismatches.append(uid)
        metrics.append(evaluate_recommendation(actual, labels, k=10))
    output = {"generated_at": iso_now(), "split": "validation", "selected_new_weights": False, "n_users": len(metrics), "mismatched_user_ids": mismatches,
              "metrics_frozen_weights_actual_inference": aggregate_metrics(metrics), "hybrid_config_sha256": file_sha256(settings.models_dir / "hybrid_config.json"),
              "note": "Audit only. Existing frozen config remains unchanged; this is not a new grid-search run."}
    write_json(settings.reports_dir / "validation-scoring-audit.json", output)
    print(output)
    if mismatches:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
