"""Latih fitur, pilih bobot hybrid di validation, lalu evaluasi di test.

Alur (PRD bagian 11):
1. Latih representasi content + collaborative + popularity pada train.
2. Tuning bobot hanya pada validation split.
3. Bekukan bobot di ``artifacts/models/hybrid_config.json``.
4. Jalankan evaluasi ranking/basket/ablation pada test split.

Jalankan: ``python scripts/train.py`` (atau ``make train``).
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from rasa.config import settings  # noqa: E402
from rasa.data.schema import load_processed_dataset  # noqa: E402
from rasa.evaluation.runner import OfflineEvaluator  # noqa: E402
from rasa.evaluation.tuning import tune_weights  # noqa: E402
from rasa.features.builder import train_feature_artifacts  # noqa: E402
from rasa.ranking.ranker import HybridRanker  # noqa: E402
from rasa.utils import iso_now, read_json, write_json  # noqa: E402


def build_ranker(weights: dict[str, float]) -> HybridRanker:
    from rasa.services.model_registry import ModelRegistry

    registry = ModelRegistry().load()
    if not registry.ready:
        raise RuntimeError(f"Artifact model gagal dimuat: {registry.error}")
    config = dict(registry.ranker.config)
    config["weights"] = weights
    return HybridRanker(
        registry.content, registry.collaborative, registry.popularity, config=config
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Latih dan evaluasi model RASA")
    parser.add_argument("--skip-tuning", action="store_true", help="Pakai bobot yang tersimpan")
    parser.add_argument("--skip-evaluation", action="store_true", help="Lewati evaluasi test")
    parser.add_argument("--tuning-users", type=int, default=180, help="Jumlah pengguna validasi")
    parser.add_argument(
        "--basket-missions", type=int, default=None, help="Jumlah misi evaluasi keranjang"
    )
    args = parser.parse_args()

    started = time.perf_counter()
    bundle = load_processed_dataset()

    print("[1/3] Melatih artifact fitur (train-only)...")
    manifest = train_feature_artifacts(bundle)

    weights_path = settings.models_dir / "hybrid_config.json"
    if args.skip_tuning and weights_path.exists():
        tuning = read_json(weights_path, {})
        print(f"[2/3] Memakai bobot tersimpan: {tuning.get('weights')}")
    else:
        print("[2/3] Tuning bobot pada validation split...")
        ranker = build_ranker(dict(settings.get("ranking.weights", {})))
        tuning = tune_weights(
            ranker,
            bundle.catalog,
            bundle.users,
            bundle.train,
            bundle.validation,
            k=int(settings.get("evaluation.primary_k", 10)),
            max_users=args.tuning_users,
            seed=settings.seed,
        )
        tuning["trained_at"] = iso_now()
        tuning["model_version"] = manifest.get("model_version", settings.model_version)
        tuning["dataset_version"] = manifest.get("dataset_version", settings.dataset.version)
        write_json(weights_path, tuning)
        print(
            f"      Bobot terpilih: {tuning['weights']} "
            f"(validation NDCG@10={tuning['selected_metrics'].get('ndcg@10', 0):.4f})"
        )

    payload = None
    if not args.skip_evaluation:
        print("[3/3] Evaluasi pada test split (ranking, basket, ablation)...")
        tuned = build_ranker({key: float(value) for key, value in tuning["weights"].items()})
        evaluator = OfflineEvaluator(bundle, tuned, k=int(settings.get("evaluation.primary_k", 10)))
        payload = evaluator.run(basket_missions=args.basket_missions)
        best = payload["ranking"].get("EXP-006", {}).get("metrics", {})
        print(
            f"      EXP-006 hybrid_mission: NDCG@10={best.get('ndcg@10', 0):.4f}, "
            f"Recall@10={best.get('recall@10', 0):.4f}"
        )

    training = {
        "trained_at": iso_now(),
        "runtime_seconds": round(time.perf_counter() - started, 1),
        "seed": settings.seed,
        "dataset_version": manifest.get("dataset_version"),
        "model_version": manifest.get("model_version"),
        "weights": tuning.get("weights"),
        "validation": tuning.get("selected_metrics"),
        "validation_ci": tuning.get("selected_ndcg_ci"),
        "evaluation": (
            {
                "ranking": {
                    key: value.get("metrics") for key, value in payload["ranking"].items()
                },
                "baskets": {
                    key: {
                        "budget_feasibility_rate": value.get("budget_feasibility_rate"),
                        "required_category_coverage": value.get("required_category_coverage"),
                    }
                    for key, value in payload["baskets"].items()
                },
            }
            if payload
            else read_json(settings.reports_dir / "training.json", {}).get("evaluation")
        ),
        "notes": [
            "Bobot dipilih pada validation split; test split hanya dipakai untuk pelaporan.",
            "Seluruh data sintetis; angka tidak merepresentasikan marketplace nyata.",
        ],
    }
    write_json(settings.reports_dir / "training.json", training)
    print(f"Selesai dalam {training['runtime_seconds']} detik.")


if __name__ == "__main__":
    main()
