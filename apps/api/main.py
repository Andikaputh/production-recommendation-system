"""Entry point uvicorn: ``uvicorn apps.api.main:app --reload``."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from rasa.api.app import app  # noqa: E402

__all__ = ["app"]
