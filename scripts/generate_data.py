"""Bangun dataset sintetis + split temporal + laporan kualitas data.

Jalankan: ``python scripts/generate_data.py`` (atau ``make data``).
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
    parser = argparse.ArgumentParser(description="Generate dataset sintetis RASA")
    parser.add_argument("--seed", type=int, default=settings.seed)
    parser.add_argument("--products", type=int, default=settings.dataset.n_products)
    args = parser.parse_args()

    manifest = generate_dataset(seed=args.seed, n_products=args.products)
    print(f"Dataset mentah: {manifest['n_events']} event, {manifest['n_products']} produk")

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
        f"Kualitas data: {summary['passed']}/{summary['total_checks']} lulus, "
        f"{summary['warnings']} peringatan, {summary['critical_failures']} kegagalan kritis"
    )
    if not summary["passed_all_critical"]:
        raise SystemExit("Pemeriksaan kualitas data gagal.")


if __name__ == "__main__":
    main()
