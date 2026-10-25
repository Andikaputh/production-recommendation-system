"""Konfigurasi terpusat RASA.

Konfigurasi dibaca dari ``configs/default.yaml`` dan dapat ditimpa oleh variabel
lingkungan. Semua jalur bersifat relatif terhadap akar repositori agar artefak
dan dataset dapat dipindahkan tanpa mengubah kode.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml

ROOT_DIR = Path(__file__).resolve().parents[2]
CONFIG_PATH = Path(os.getenv("RASA_CONFIG", ROOT_DIR / "configs" / "default.yaml"))


@dataclass(frozen=True)
class DatasetConfig:
    name: str
    version: str
    anchor_date: str
    n_categories: int
    n_products: int
    n_merchants: int
    n_users: int
    cold_user_fraction: float
    late_product_fraction: float
    n_interactions_target: int
    interaction_window_days: int
    synthetic: bool


@dataclass(frozen=True)
class Settings:
    raw: dict[str, Any] = field(default_factory=dict)
    config_path: Path = CONFIG_PATH
    root_dir: Path = ROOT_DIR

    # ---- akses umum -----------------------------------------------------
    def get(self, dotted: str, default: Any = None) -> Any:
        node: Any = self.raw
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    @property
    def seed(self) -> int:
        return int(self.raw.get("seed", 42))

    @property
    def dataset(self) -> DatasetConfig:
        data = self.raw["dataset"]
        return DatasetConfig(**data)

    # ---- jalur ----------------------------------------------------------
    def path(self, key: str) -> Path:
        configured = self.raw.get("paths", {}).get(key, key)
        path = Path(configured)
        if not path.is_absolute():
            path = self.root_dir / path
        return path

    @property
    def raw_dir(self) -> Path:
        return self.path("raw")

    @property
    def processed_dir(self) -> Path:
        return self.path("processed")

    @property
    def sample_dir(self) -> Path:
        return self.path("sample")

    @property
    def artifacts_dir(self) -> Path:
        return self.path("artifacts")

    @property
    def models_dir(self) -> Path:
        return self.artifacts_dir / "models"

    @property
    def reports_dir(self) -> Path:
        return self.artifacts_dir / "reports"

    @property
    def experiments_dir(self) -> Path:
        return self.path("experiments")

    @property
    def scenarios_path(self) -> Path:
        return self.root_dir / "configs" / "scenarios.json"

    # ---- koneksi & runtime ---------------------------------------------
    @property
    def database_url(self) -> str:
        explicit = os.getenv("RASA_DATABASE_URL") or os.getenv("DATABASE_URL")
        if explicit:
            return explicit
        default_path = self.root_dir / "data" / "rasa.db"
        return f"sqlite:///{default_path.as_posix()}"

    @property
    def cors_origins(self) -> list[str]:
        env = os.getenv("RASA_CORS_ORIGINS")
        if env:
            return [origin.strip() for origin in env.split(",") if origin.strip()]
        return list(self.get("api.cors_origins", ["*"]))

    @property
    def environment(self) -> Literal["development", "test", "production"]:
        value = os.getenv("RASA_ENV", "development").lower()
        if value in {"development", "test", "production"}:
            return value  # type: ignore[return-value]
        return "development"

    @property
    def model_version(self) -> str:
        return os.getenv("RASA_MODEL_VERSION", "hybrid-v1")

    def ensure_directories(self) -> None:
        for directory in (
            self.raw_dir,
            self.processed_dir,
            self.sample_dir,
            self.models_dir,
            self.reports_dir,
            self.experiments_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"Konfigurasi tidak ditemukan: {CONFIG_PATH}")
    with CONFIG_PATH.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    settings = Settings(raw=raw, config_path=CONFIG_PATH, root_dir=ROOT_DIR)
    settings.ensure_directories()
    return settings


settings = get_settings()
