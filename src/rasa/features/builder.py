"""Feature representation: content-based dan collaborative filtering.

Semua transformasi di-fit HANYA pada data training (anti-leakage) lalu
disimpan sebagai artefak berversi. Inference memuat artefak, bukan melatih ulang.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from scipy import sparse
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import OneHotEncoder

from rasa.config import settings
from rasa.data.schema import POSITIVE_EVENTS
from rasa.utils import iso_now, normalize, write_json


def build_item_text(catalog: pd.DataFrame) -> pd.Series:
    def _row_text(row: pd.Series) -> str:
        tags = " ".join(row.get("tags") or [])
        return " ".join(
            str(part)
            for part in (
                row["product_name"],
                row["category_name"],
                row["subcategory"],
                row["brand"],
                row["description"],
                row.get("style", ""),
                row.get("color", ""),
                row.get("material", ""),
                tags,
            )
            if str(part).strip()
        )

    return catalog.apply(_row_text, axis=1)


class ContentModel:
    """TF-IDF + kategorikal + fitur numerik, digabung menjadi vektor konten."""

    def __init__(self, seed: int | None = None) -> None:
        self.seed = settings.seed if seed is None else seed
        self.tfidf: TfidfVectorizer | None = None
        self.onehot: OneHotEncoder | None = None
        self.item_ids: list[str] = []
        self.item_index: dict[str, int] = {}
        self.item_matrix: sparse.csr_matrix | None = None
        self.n_text_features: int = 0
        self.numeric_stats: dict[str, dict[str, float]] = {}
        self.version = "content-v1"

    def _numeric_block(self, catalog: pd.DataFrame, fit: bool = False) -> np.ndarray:
        price_log = np.log1p(catalog["price"].to_numpy(dtype=float))
        review_log = np.log1p(catalog["review_count"].to_numpy(dtype=float))
        rating = catalog["rating"].to_numpy(dtype=float)
        warranty = catalog["warranty_months"].to_numpy(dtype=float)
        eco = catalog["eco_friendly"].astype(float).to_numpy()
        raw = np.column_stack([price_log, review_log, rating, warranty, eco])
        if fit:
            self.numeric_stats = {
                "min": raw.min(axis=0).tolist(),
                "max": raw.max(axis=0).tolist(),
            }
        low = np.asarray(self.numeric_stats["min"], dtype=float)
        high = np.asarray(self.numeric_stats["max"], dtype=float)
        denom = np.where(high - low < 1e-9, 1.0, high - low)
        block = (raw - low) / denom
        weights = np.array([0.30, 0.20, 0.30, 0.10, 0.10])
        return np.clip(block, 0.0, 1.0) * weights

    def fit(self, catalog: pd.DataFrame) -> ContentModel:
        catalog = catalog.reset_index(drop=True)
        self.item_ids = catalog["product_id"].tolist()
        self.item_index = {product_id: idx for idx, product_id in enumerate(self.item_ids)}

        self.tfidf = TfidfVectorizer(
            max_features=int(settings.get("features.tfidf.max_features", 4000)),
            ngram_range=tuple(settings.get("features.tfidf.ngram_range", [1, 2])),
            min_df=int(settings.get("features.tfidf.min_df", 2)),
            sublinear_tf=bool(settings.get("features.tfidf.sublinear_tf", True)),
            strip_accents="unicode",
        )
        text_matrix = self.tfidf.fit_transform(build_item_text(catalog))
        self.n_text_features = text_matrix.shape[1]

        categorical = catalog[["category_id", "subcategory", "style", "color", "material", "brand"]].astype(str)
        self.onehot = OneHotEncoder(handle_unknown="ignore", sparse_output=True)
        categorical_matrix = self.onehot.fit_transform(categorical)
        numeric_matrix = sparse.csr_matrix(self._numeric_block(catalog, fit=True))

        item_matrix = sparse.hstack(
            [
                text_matrix * 0.70,
                categorical_matrix * 0.35,
                numeric_matrix * 0.20,
            ],
            format="csr",
        )
        norms = np.sqrt(item_matrix.multiply(item_matrix).sum(axis=1)).A1
        norms[norms == 0] = 1.0
        self.item_matrix = sparse.diags(1.0 / norms) @ item_matrix
        self.item_matrix = self.item_matrix.tocsr().astype(np.float32)
        return self

    # ------------------------------------------------------------------
    def transform_query(self, text: str) -> sparse.csr_matrix:
        if self.tfidf is None:
            raise RuntimeError("ContentModel belum di-fit.")
        vector = self.tfidf.transform([text or ""])
        norm = float(np.sqrt(vector.multiply(vector).sum()))
        if norm > 0:
            vector = vector / norm
        return vector.tocsr()

    def text_scores(self, text: str) -> np.ndarray:
        if self.tfidf is None or self.item_matrix is None:
            raise RuntimeError("ContentModel belum di-fit.")
        query = self.transform_query(text)
        # Skor cosine terhadap blok TF-IDF item (bukan seluruh matriks).
        tfidf_block = self.item_matrix[:, : self.n_text_features]
        scores = np.asarray((tfidf_block @ query.T).todense()).ravel()
        return np.clip(scores, 0.0, 1.0)

    def profile_from_items(self, weights: dict[str, float]) -> np.ndarray | None:
        if self.item_matrix is None:
            return None
        indices = [self.item_index[product_id] for product_id in weights if product_id in self.item_index]
        if not indices:
            return None
        vector = np.zeros(self.item_matrix.shape[1], dtype=np.float32)
        total = 0.0
        for product_id, weight in weights.items():
            idx = self.item_index.get(product_id)
            if idx is None:
                continue
            vector += self.item_matrix.getrow(idx).toarray().ravel() * float(weight)
            total += abs(float(weight))
        if total == 0:
            return None
        vector /= total
        norm = float(np.linalg.norm(vector))
        if norm > 0:
            vector /= norm
        return vector

    def scores_for_profile(self, profile: np.ndarray | None) -> np.ndarray:
        if profile is None or self.item_matrix is None:
            return np.zeros(len(self.item_index))
        return np.clip(np.asarray(self.item_matrix @ profile).ravel(), 0.0, 1.0)

    def item_similarity(self, product_id: str) -> np.ndarray:
        idx = self.item_index.get(product_id)
        if idx is None or self.item_matrix is None:
            return np.zeros(len(self.item_index))
        return np.clip(np.asarray(self.item_matrix @ self.item_matrix.getrow(idx).T.toarray().ravel()).ravel(), 0, 1)

    # ------------------------------------------------------------------
    def save(self, path: Path | None = None) -> Path:
        path = path or (settings.models_dir / "content_model.joblib")
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(
            {
                "tfidf": self.tfidf,
                "onehot": self.onehot,
                "item_ids": self.item_ids,
                "item_matrix": self.item_matrix,
                "numeric_stats": self.numeric_stats,
                "n_text_features": self.n_text_features,
                "version": self.version,
                "seed": self.seed,
            },
            path,
            compress=3,
        )
        return path

    @classmethod
    def load(cls, path: Path | None = None) -> ContentModel:
        path = path or (settings.models_dir / "content_model.joblib")
        if not path.exists():
            raise FileNotFoundError(f"Artifact content model tidak ditemukan: {path}")
        payload = joblib.load(path)
        model = cls(seed=int(payload.get("seed", settings.seed)))
        model.tfidf = payload["tfidf"]
        model.onehot = payload["onehot"]
        model.item_ids = payload["item_ids"]
        model.item_index = {product_id: idx for idx, product_id in enumerate(model.item_ids)}
        model.item_matrix = payload["item_matrix"]
        model.numeric_stats = payload["numeric_stats"]
        model.n_text_features = int(payload.get("n_text_features", 0))
        if not model.n_text_features and model.tfidf is not None:
            model.n_text_features = len(model.tfidf.vocabulary_)
        model.version = payload.get("version", "content-v1")
        return model

    @property
    def n_items(self) -> int:
        return len(self.item_ids)


@dataclass
class CollaborativeArtifacts:
    model_version: str
    trained_at: str
    n_users: int
    n_items: int
    n_components: int
    explained_variance: float


class CollaborativeModel:
    """Matrix factorization (TruncatedSVD) + item-item similarity.

    Untuk pengguna baru / sesi anonim, skor CF dihitung dari kemiripan item
    terhadap produk yang telah diberi feedback dalam sesi (session-based CF).
    """

    def __init__(self, seed: int | None = None) -> None:
        self.seed = settings.seed if seed is None else seed
        self.user_ids: list[str] = []
        self.user_index: dict[str, int] = {}
        self.item_ids: list[str] = []
        self.item_index: dict[str, int] = {}
        self.user_factors: np.ndarray | None = None
        self.item_factors: np.ndarray | None = None
        self.item_similarity: np.ndarray | None = None
        self.user_interaction_counts: dict[str, int] = {}
        self.version = "cf-svd-v1"
        self.meta: dict[str, Any] = {}

    def fit(self, train_events: pd.DataFrame, catalog: pd.DataFrame) -> CollaborativeModel:
        event_weights = settings.get("features.event_weights", {})
        positives = train_events[train_events["event_type"].isin(POSITIVE_EVENTS)].copy()
        positives["weight"] = positives["event_type"].map(event_weights).fillna(1.0).astype(float)

        self.item_ids = catalog["product_id"].tolist()
        self.item_index = {product_id: idx for idx, product_id in enumerate(self.item_ids)}
        self.user_ids = sorted(positives["user_id"].dropna().unique().tolist())
        self.user_index = {user_id: idx for idx, user_id in enumerate(self.user_ids)}

        rows = positives["user_id"].map(self.user_index).to_numpy()
        cols = positives["product_id"].map(self.item_index).to_numpy()
        values = positives["weight"].to_numpy(dtype=np.float32)
        matrix = sparse.csr_matrix(
            (values, (rows, cols)), shape=(len(self.user_ids), len(self.item_ids)), dtype=np.float32
        )
        # Gabungkan event berulang pada user-item yang sama.
        matrix.sum_duplicates()

        self.user_interaction_counts = (
            positives.groupby("user_id")["product_id"].nunique().astype(int).to_dict()
        )

        n_components = int(settings.get("features.collaborative.n_components", 32))
        n_components = max(2, min(n_components, min(matrix.shape) - 1))
        svd = TruncatedSVD(n_components=n_components, random_state=self.seed)
        self.user_factors = svd.fit_transform(matrix).astype(np.float32)
        self.item_factors = svd.components_.T.astype(np.float32)

        # Item-item similarity dari faktor laten (lebih stabil untuk data sparse).
        norms = np.linalg.norm(self.item_factors, axis=1)
        norms[norms == 0] = 1.0
        normalized = self.item_factors / norms[:, None]
        similarity = normalized @ normalized.T
        np.fill_diagonal(similarity, 0.0)
        top_k = int(settings.get("features.collaborative.item_similarity_top_k", 40))
        if top_k < similarity.shape[1]:
            threshold = np.partition(similarity, -top_k, axis=1)[:, -top_k][:, None]
            similarity = np.where(similarity >= threshold, similarity, 0.0)
        self.item_similarity = np.clip(similarity, 0.0, 1.0).astype(np.float32)

        self.meta = {
            "model_version": self.version,
            "trained_at": iso_now(),
            "n_users": len(self.user_ids),
            "n_items": len(self.item_ids),
            "n_components": n_components,
            "explained_variance": round(float(svd.explained_variance_ratio_.sum()), 4),
            "n_interaction_events": int(len(positives)),
            "matrix_sparsity": round(
                float(1.0 - matrix.nnz / (matrix.shape[0] * matrix.shape[1])), 4
            ),
        }
        return self

    def has_user(self, user_id: str | None) -> bool:
        return bool(user_id) and user_id in self.user_index

    def user_interaction_count(self, user_id: str | None) -> int:
        if not user_id:
            return 0
        return int(self.user_interaction_counts.get(user_id, 0))

    def score_user(self, user_id: str | None) -> np.ndarray:
        if not self.has_user(user_id) or self.user_factors is None or self.item_factors is None:
            return np.zeros(len(self.item_ids), dtype=np.float32)
        idx = self.user_index[user_id]  # type: ignore[index]
        return np.asarray(self.item_factors @ self.user_factors[idx], dtype=np.float32)

    def score_session(self, session_weights: dict[str, float] | None) -> np.ndarray:
        if not session_weights or self.item_similarity is None:
            return np.zeros(len(self.item_ids), dtype=np.float32)
        vectors = []
        weights = []
        for product_id, weight in session_weights.items():
            idx = self.item_index.get(product_id)
            if idx is None:
                continue
            vectors.append(self.item_similarity[idx])
            weights.append(float(weight))
        if not vectors:
            return np.zeros(len(self.item_ids), dtype=np.float32)
        weights_array = np.asarray(weights, dtype=np.float32)
        if weights_array.sum() == 0:
            return np.zeros(len(self.item_ids), dtype=np.float32)
        return np.average(np.vstack(vectors), axis=0, weights=weights_array).astype(np.float32)

    def save(self, path: Path | None = None) -> Path:
        path = path or (settings.models_dir / "collaborative_model.joblib")
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(
            {
                "user_ids": self.user_ids,
                "item_ids": self.item_ids,
                "user_factors": self.user_factors,
                "item_factors": self.item_factors,
                "item_similarity": self.item_similarity,
                "user_interaction_counts": self.user_interaction_counts,
                "version": self.version,
                "seed": self.seed,
                "meta": self.meta,
            },
            path,
            compress=3,
        )
        return path

    @classmethod
    def load(cls, path: Path | None = None) -> CollaborativeModel:
        path = path or (settings.models_dir / "collaborative_model.joblib")
        if not path.exists():
            raise FileNotFoundError(f"Artifact collaborative model tidak ditemukan: {path}")
        payload = joblib.load(path)
        model = cls(seed=int(payload.get("seed", settings.seed)))
        model.user_ids = payload["user_ids"]
        model.user_index = {user_id: idx for idx, user_id in enumerate(model.user_ids)}
        model.item_ids = payload["item_ids"]
        model.item_index = {product_id: idx for idx, product_id in enumerate(model.item_ids)}
        model.user_factors = payload["user_factors"]
        model.item_factors = payload["item_factors"]
        model.item_similarity = payload["item_similarity"]
        model.user_interaction_counts = payload.get("user_interaction_counts", {})
        model.version = payload.get("version", "cf-svd-v1")
        model.meta = payload.get("meta", {})
        return model

    @property
    def n_items(self) -> int:
        return len(self.item_ids)


class PopularityModel:
    def __init__(self) -> None:
        self.global_counts: dict[str, int] = {}
        self.category_counts: dict[str, dict[str, int]] = {}
        self.total: int = 0
        self.version = "popularity-v1"

    def fit(self, train_events: pd.DataFrame, catalog: pd.DataFrame) -> PopularityModel:
        positives = train_events[train_events["event_type"].isin(POSITIVE_EVENTS)]
        counts = positives.groupby("product_id").size()
        self.global_counts = counts.astype(int).to_dict()
        self.total = int(len(positives))
        merged = positives.merge(catalog[["product_id", "category_id"]], on="product_id", how="left")
        self.category_counts = {
            category_id: group.groupby("product_id").size().astype(int).to_dict()
            for category_id, group in merged.groupby("category_id")
        }
        return self

    def global_scores(self, catalog: pd.DataFrame) -> np.ndarray:
        values = np.array([self.global_counts.get(pid, 0) for pid in catalog["product_id"]], dtype=float)
        return normalize(values)

    def category_scores(self, catalog: pd.DataFrame, categories: list[str] | None = None) -> np.ndarray:
        """Popularitas relatif di dalam kategori (share, bukan count mentah).

        Membagi dengan total interaksi kategori membuat kategori kecil dan besar
        dapat dibandingkan secara adil saat memilih produk lintas kategori misi.
        """
        values = np.zeros(len(catalog), dtype=float)
        category_totals = {
            category_id: float(sum(counts.values()))
            for category_id, counts in self.category_counts.items()
        }
        for idx, (product_id, category_id) in enumerate(
            zip(catalog["product_id"], catalog["category_id"], strict=False)
        ):
            if categories and category_id not in categories:
                continue
            category_counts = self.category_counts.get(category_id, {})
            total = category_totals.get(category_id, 0.0) or 1.0
            values[idx] = category_counts.get(product_id, 0) / total
        return normalize(values)

    def save(self, path: Path | None = None) -> Path:
        path = path or (settings.models_dir / "popularity_model.joblib")
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(
            {
                "global_counts": self.global_counts,
                "category_counts": self.category_counts,
                "total": self.total,
                "version": self.version,
            },
            path,
        )
        return path

    @classmethod
    def load(cls, path: Path | None = None) -> PopularityModel:
        path = path or (settings.models_dir / "popularity_model.joblib")
        if not path.exists():
            raise FileNotFoundError(f"Artifact popularity model tidak ditemukan: {path}")
        payload = joblib.load(path)
        model = cls()
        model.global_counts = payload["global_counts"]
        model.category_counts = payload["category_counts"]
        model.total = payload.get("total", 0)
        model.version = payload.get("version", "popularity-v1")
        return model

    def as_dict(self) -> dict:
        return {
            "version": self.version,
            "total_positive_events": self.total,
            "n_products_with_history": len(self.global_counts),
            "median_interactions": float(np.median(list(self.global_counts.values()))) if self.global_counts else 0.0,
        }


def train_feature_artifacts(bundle, output_dir: Path | None = None) -> dict:
    """Latih seluruh representasi fitur dari data training saja."""
    output_dir = output_dir or settings.models_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    content = ContentModel().fit(bundle.catalog)
    content.save(output_dir / "content_model.joblib")

    collaborative = CollaborativeModel().fit(bundle.train, bundle.catalog)
    collaborative.save(output_dir / "collaborative_model.joblib")

    popularity = PopularityModel().fit(bundle.train, bundle.catalog)
    popularity.save(output_dir / "popularity_model.joblib")

    manifest = {
        "model_version": settings.model_version,
        "trained_at": iso_now(),
        "dataset_version": settings.dataset.version,
        "seed": settings.seed,
        "n_items": len(bundle.catalog),
        "n_users": int(bundle.train["user_id"].nunique()),
        "artifacts": {
            "content": content.version,
            "collaborative": collaborative.version,
            "popularity": popularity.version,
        },
        "collaborative_meta": collaborative.meta,
        "popularity_meta": popularity.as_dict(),
        "training_window": {
            "start": str(bundle.train["event_timestamp"].min()),
            "end": str(bundle.train["event_timestamp"].max()),
        },
        "notes": [
            "TF-IDF, one-hot encoder, dan statistik numerik di-fit hanya pada data training.",
            "Popularity dihitung hanya dari event positif pada data training.",
            "Harga dan stok adalah data simulasi.",
        ],
    }
    write_json(output_dir / "feature_manifest.json", manifest)
    return manifest


def load_feature_bundle() -> tuple[ContentModel, CollaborativeModel, PopularityModel, dict]:
    content = ContentModel.load()
    collaborative = CollaborativeModel.load()
    popularity = PopularityModel.load()
    manifest_path = settings.models_dir / "feature_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    return content, collaborative, popularity, manifest
