"""Compare optimizer pruning policies on the same frozen synthetic mission sample."""
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from rasa.config import settings  # noqa: E402
from rasa.data.schema import load_processed_dataset  # noqa: E402
from rasa.evaluation.runner import generate_evaluation_missions  # noqa: E402
from rasa.optimization.basket import _ilp_solve, _prune_candidates  # noqa: E402
from rasa.services.catalog import CatalogService  # noqa: E402
from rasa.services.model_registry import ModelRegistry  # noqa: E402
from rasa.utils import file_sha256, iso_now, write_json  # noqa: E402


def main():
    registry = ModelRegistry().load()
    if not registry.ready:
        raise SystemExit(registry.error)
    bundle = load_processed_dataset()
    catalog = CatalogService().load_from_bundle(bundle).catalog
    missions = generate_evaluation_missions(bundle, 120, seed=settings.seed)
    records = []
    limit = int(settings.get("optimization.max_candidates_per_category", 14))
    for index, mission in enumerate(missions):
        scored = registry.ranker.rank(catalog, mission, strategy="hybrid_mission").scored
        policies = {
            "old_top_score_only": scored.groupby("category_id", group_keys=False).head(limit),
            "price_and_merchant_preserving": _prune_candidates(scored, mission),
            "all_retrieved_candidates": scored,
        }
        outcomes = {}
        for label, candidates in policies.items():
            selected, solver, objective = _ilp_solve(candidates, mission, float(settings.get("optimization.lambda_merchant", .015)), float(settings.get("optimization.lambda_budget_slack", .02)), 2.0)
            outcomes[label] = {"candidate_count": len(candidates), "feasible": selected is not None, "solver": solver, "objective": objective}
        records.append({"mission_index": index, "outcomes": outcomes})
    totals = {key: sum(r["outcomes"][key]["feasible"] for r in records) for key in policies}
    write_json(settings.reports_dir / "candidate-pruning-audit.json", {
        "generated_at": iso_now(), "seed": settings.seed, "n_missions": len(missions), "feasible_counts": totals,
        "mission_hash": hashlib.sha256(json.dumps([m.to_dict() for m in missions], sort_keys=True).encode()).hexdigest(),
        "model_config_sha256": file_sha256(settings.models_dir / "hybrid_config.json"),
        "optimizer_sha256": file_sha256(settings.root_dir / "src/rasa/optimization/basket.py"),
        "note": "Same eligible retrieved candidates for all policies. Full means after retrieval filters/cap; no global guarantee. Solver statuses retained; timeout is not proof of infeasibility. No tuning on these results.",
        "records": records,
    })
    print(totals)


if __name__ == "__main__":
    main()
