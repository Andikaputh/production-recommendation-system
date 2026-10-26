"""Local operator import; OS access to the database is required. No external traffic."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from rasa.db.session import init_db, session_scope  # noqa: E402
from rasa.services.pilot import CatalogImport, import_catalog  # noqa: E402

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path)
    parser.add_argument("--apply", action="store_true", help="Write only after full validation; default dry run")
    parser.add_argument("--real", action="store_true", help="Declare data as real merchant data; default synthetic")
    args = parser.parse_args()
    init_db()
    with session_scope() as db:
        report = import_catalog(db, CatalogImport(csv_text=args.file.read_text(encoding="utf-8-sig"), synthetic=not args.real, dry_run=not args.apply))
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if not report["valid"]:
        raise SystemExit(1)
