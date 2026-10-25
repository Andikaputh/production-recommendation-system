"""Seed database demo (SQLite default) dari dataset dan artefak."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from rasa.config import settings  # noqa: E402
from rasa.db.seed import seed_database  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed database RASA")
    parser.add_argument("--keep", action="store_true", help="Jangan hapus tabel yang ada")
    parser.add_argument("--no-events", action="store_true", help="Lewati event interaksi")
    args = parser.parse_args()

    counts = seed_database(drop=not args.keep, include_events=not args.no_events)
    print(f"Database: {settings.database_url}")
    for name, value in counts.items():
        print(f"  {name}: {value}")


if __name__ == "__main__":
    main()
