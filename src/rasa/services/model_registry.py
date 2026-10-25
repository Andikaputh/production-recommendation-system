"""Registry artefak model untuk inference (tanpa training saat request)."""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import RLock
from typing import Any

from rasa.config import settings
from rasa.features.builder import (
    CollaborativeModel,
    ContentModel,
    PopularityModel,
    load_feature_bundle,
)
from rasa.ranking.ranker import HybridRanker
from rasa.utils import read_json


@dataclass
class ModelRegistry:
    content: ContentModel | None = None
    collaborative: CollaborativeModel | None = None
    popularity: PopularityModel | None = None
    manifest: dict[str, Any] = field(default_factory=dict)
    hybrid_config: dict[str, Any] = field(default_factory=dict)
    ready: bool = False
    error: str | None = None
    _lock: RLock = field(default_factory=RLock)
    _ranker: HybridRanker | None = None

    def load(self) -> ModelRegistry:
        with self._lock:
            try:
                content, collaborative, popularity, manifest = load_feature_bundle()
                hybrid = read_json(settings.models_dir / "hybrid_config.json", {}) or {}
                self.content = content
                self.collaborative = collaborative
                self.popularity = popularity
                self.manifest = manifest
                self.hybrid_config = hybrid
                weights = hybrid.get("weights") or settings.get("ranking.weights", {})
                self._ranker = HybridRanker(
                    content,
                    collaborative,
                    popularity,
                    config={
                        "weights": weights,
                        "top_k": settings.get("ranking.top_k", 10),
                        "candidate_limit_per_category": settings.get(
                            "ranking.candidate_limit_per_category", 60
                        ),
                        "min_interactions": settings.get("ranking.cold_start.min_interactions", 3),
                        "exposure_alpha": settings.get(
                            "ranking.controlled_exposure.alpha", 0.08
                        ),
                        "exposure_max_share": settings.get(
                            "ranking.controlled_exposure.max_share", 0.20
                        ),
                        "low_history_quantile": settings.get(
                            "ranking.controlled_exposure.low_history_quantile", 0.40
                        ),
                        "hybrid_baseline_collaborative": settings.get(
                            "ranking.hybrid_baseline.collaborative", 0.25
                        ),
                        "hybrid_baseline_content": settings.get(
                            "ranking.hybrid_baseline.content", 0.55
                        ),
                        "hybrid_baseline_quality": settings.get(
                            "ranking.hybrid_baseline.quality", 0.20
                        ),
                    },
                )
                self.ready = True
                self.error = None
            except Exception as exc:
                self.ready = False
                self.error = f"{type(exc).__name__}: {exc}"
            return self

    @property
    def ranker(self) -> HybridRanker:
        if not self.ready or self._ranker is None:
            raise RuntimeError(f"Model belum siap dimuat: {self.error}")
        return self._ranker

    @property
    def model_version(self) -> str:
        return str(self.manifest.get("model_version") or settings.model_version)

    @property
    def dataset_version(self) -> str:
        return str(self.manifest.get("dataset_version") or settings.dataset.version)

    @property
    def trained_at(self) -> str | None:
        return self.manifest.get("trained_at")

    def status(self) -> dict[str, Any]:
        return {
            "ready": self.ready,
            "model_version": self.model_version if self.ready else None,
            "dataset_version": self.dataset_version if self.ready else None,
            "trained_at": self.trained_at,
            "error": self.error,
            "components": {
                "content": self.content.version if self.content else None,
                "collaborative": self.collaborative.version if self.collaborative else None,
                "popularity": self.popularity.version if self.popularity else None,
            },
            "weights": (self.hybrid_config.get("weights") if self.hybrid_config else None),
        }


registry = ModelRegistry()
