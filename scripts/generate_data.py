"""Build the synthetic dataset, temporal splits, and data-quality report.

Run ``python scripts/generate_data.py`` or ``make data``.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from rasa.config import settings  # noqa: E402
from rasa.data.generate import generate_dataset  # noqa: E402
from rasa.data.quality import render_markdown, run_data_quality_checks  # noqa: E402
from rasa.data.schema import build_dataset  # noqa: E402
from rasa.utils import write_json  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the synthetic RASA dataset")
    parser.add_argument("--seed", type=int, default=settings.seed)
    parser.add_argument("--products", type=int, default=settings.dataset.n_products)
    args = parser.parse_args()

    manifest = generate_dataset(seed=args.seed, n_products=args.products)
    print(f"Raw dataset: {manifest['n_events']} events, {manifest['n_products']} products")

    bundle = build_dataset(write=True)
    print(
        "Split temporal: "
        f"train={bundle.summary['n_train']} validation={bundle.summary['n_validation']} "
        f"test={bundle.summary['n_test']}"
    )

    report = run_data_quality_checks(bundle)
    write_json(settings.reports_dir / "data_quality.json", report)
    docs_dir = settings.root_dir / "docs" / "dataset"
    docs_dir.mkdir(parents=True, exist_ok=True)
    (docs_dir / "data-quality-report.md").write_text(render_markdown(report), encoding="utf-8")

    summary = report["summary"]
    print(
        f"Data quality: {summary['passed']}/{summary['total_checks']} passed, "
        f"{summary['warnings']} warnings, {summary['critical_failures']} critical failures"
    )
    if not summary["passed_all_critical"]:
        raise SystemExit("Data-quality checks failed.")


if __name__ == "__main__":
    main()
