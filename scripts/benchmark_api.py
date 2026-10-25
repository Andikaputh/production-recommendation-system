"""Smoke benchmark endpoint rekomendasi pada process lokal.

Menjalankan lifespan aplikasi, warm-up sekali, lalu mengukur beberapa request.
Exit code non-zero bila p95 melewati target konfigurasi.
"""

from __future__ import annotations

import argparse
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from rasa.api.app import app  # noqa: E402
from rasa.config import settings  # noqa: E402
from rasa.utils import read_json  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark API rekomendasi RASA")
    parser.add_argument("--requests", type=int, default=10)
    parser.add_argument("--scenario", type=int, default=0)
    args = parser.parse_args()

    scenarios = (read_json(settings.scenarios_path, {}) or {}).get("scenarios", [])
    scenario = scenarios[args.scenario]
    payload = {
        "mission": scenario["mission"],
        "preferences": scenario.get("preferences", {}),
        "context": {
            "session_id": "local-benchmark",
            "strategy": "hybrid_mission",
            "top_k": 10,
            "include_comparison": False,
        },
    }

    latencies: list[float] = []
    with TestClient(app) as client:
        warmup = client.post("/api/v1/recommendations", json=payload)
        warmup.raise_for_status()
        for _ in range(max(1, args.requests)):
            started = time.perf_counter()
            response = client.post("/api/v1/recommendations", json=payload)
            response.raise_for_status()
            latencies.append((time.perf_counter() - started) * 1000)

    p95 = float(np.percentile(latencies, 95))
    target = float(settings.get("api.recommendation_timeout_seconds", 2.5)) * 1000
    print(f"requests={len(latencies)} mean_ms={statistics.mean(latencies):.1f} p95_ms={p95:.1f} target_ms={target:.1f}")
    if p95 > target:
        raise SystemExit(f"p95 {p95:.1f} ms melebihi target {target:.1f} ms")


if __name__ == "__main__":
    main()
