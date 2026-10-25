"""Utilitas umum: waktu, hash, pembulatan, dan I/O JSON yang aman."""

from __future__ import annotations

import hashlib
import json
import math
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np

# Tanggal acuan dataset. Semua timestamp sintetis relatif terhadap tanggal ini
# sehingga eksperimen dapat direproduksi kapan pun.
DATASET_ANCHOR = datetime(2026, 8, 1, tzinfo=UTC)


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def iso_now() -> str:
    return utcnow().isoformat(timespec="seconds") + "Z"


def to_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat(timespec="seconds")


def stable_hash(*parts: Any) -> str:
    payload = "|".join(str(part) for part in parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def short_hash(*parts: Any) -> str:
    return stable_hash(*parts)[:12]


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    if math.isnan(value) or math.isinf(value):
        return low
    return max(low, min(high, value))


def normalize(values: np.ndarray) -> np.ndarray:
    """Min-max normalization yang aman untuk array konstan."""
    values = np.asarray(values, dtype=float)
    if values.size == 0:
        return values
    low = float(np.min(values))
    high = float(np.max(values))
    if not np.isfinite(low) or not np.isfinite(high) or high - low < 1e-12:
        return np.zeros_like(values)
    return (values - low) / (high - low)


def round_idr(value: float) -> int:
    """Bulatkan rupiah ke kelipatan 500 terdekat."""
    return int(round(float(value) / 500.0) * 500)


def format_idr(value: float | int | None) -> str:
    """Format rupiah gaya Indonesia: Rp250.000."""
    if value is None:
        return "Rp-"
    return "Rp" + f"{int(round(float(value))):,}".replace(",", ".")


def file_sha256(path: Path | str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path | str, payload: Any, *, indent: int = 2) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=indent, default=str)
        handle.write("\n")
    os.replace(tmp, path)


def read_json(path: Path | str, default: Any = None) -> Any:
    path = Path(path)
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_jsonl(path: Path | str, rows: list[dict[str, Any]], *, append: bool = False) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if append else "w"
    with path.open(mode, encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def read_jsonl(path: Path | str) -> list[dict[str, Any]]:
    path = Path(path)
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def json_safe(value: Any) -> Any:
    """Ubah tipe numpy/pandas menjadi tipe JSON native secara rekursif."""
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_safe(item) for item in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, (datetime,)):
        return value.isoformat(timespec="seconds")
    if isinstance(value, np.ndarray):
        return [json_safe(item) for item in value.tolist()]
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return value


def days_before(days: float, anchor: datetime = DATASET_ANCHOR) -> datetime:
    return anchor - timedelta(days=days)
