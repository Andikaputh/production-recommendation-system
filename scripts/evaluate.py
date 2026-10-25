"""Run offline evaluation with frozen artifacts and weights."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from rasa.config import settings  # noqa: E402
from rasa.data.schema import load_processed_dataset  # noqa: E402
from rasa.evaluation.runner import OfflineEvaluator  # noqa: E402
from rasa.services.model_registry import ModelRegistry  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Run RASA offline evaluation")
    parser.add_argument("--basket-missions", type=int, default=None)
    parser.add_argument("--k", type=int, default=None)
    args = parser.parse_args()

    bundle = load_processed_dataset()
    registry = ModelRegistry().load()
    if not registry.ready:
        raise SystemExit(f"Model artifacts are not ready: {registry.error}")

    k = args.k or int(settings.get("evaluation.primary_k", 10))
    evaluator = OfflineEvaluator(bundle, registry.ranker, k=k)
    payload = evaluator.run(basket_missions=args.basket_missions)
    print(
        f"Evaluation complete: {len(payload['ranking'])} ranking experiments, "
        f"{len(payload['baskets'])} basket configurations."
    )


if __name__ == "__main__":
    main()
