"""Offline evaluation runner for ranking, catalog, basket, ablation, and A/B simulation."""

from __future__ import annotations

import copy
import time
from collections import defaultdict
from typing import Any

import numpy as np
import pandas as pd

from rasa.config import settings
from rasa.data.schema import POSITIVE_EVENTS, DatasetBundle
from rasa.evaluation.basket_metrics import summarize_baskets
from rasa.evaluation.catalog_metrics import summarize_catalog_metrics
from rasa.evaluation.ranking_metrics import (
    aggregate_metrics,
    bootstrap_ci,
    evaluate_recommendation,
)
from rasa.missions.validation import Mission, Preferences
from rasa.optimization.basket import BasketResult, naive_independent_basket, optimize_basket
from rasa.ranking.ranker import HybridRanker, simulate_mission_for_user
from rasa.services.catalog import CatalogService
from rasa.utils import iso_now, read_json, write_json

EXPERIMENT_STRATEGIES = {
    "EXP-001": ("Global Popularity", "popularity_global", "ranking"),
    "EXP-002": ("Category Popularity", "popularity_category", "ranking_and_basket"),
    "EXP-003": ("Content-Based", "content", "ranking"),
    "EXP-004": ("Collaborative Filtering", "collaborative", "ranking"),
    "EXP-005": ("Hybrid", "hybrid", "ranking"),
    "EXP-006": ("Hybrid + Mission Ranking", "hybrid_mission", "ranking_and_basket"),
    "EXP-007": ("Hybrid + Basket Optimization", "hybrid_basket", "basket"),
    "EXP-008": ("Hybrid + Controlled Exposure", "hybrid_exposure", "ranking_and_basket"),
}

METRIC_NAMES = ["precision@10", "recall@10", "ndcg@10", "map@10", "mrr", "hit_rate@10"]


def generate_evaluation_missions(
    bundle: DatasetBundle,
    n_missions: int = 120,
    seed: int = 42,
) -> list[Mission]:
    rng = np.random.default_rng(seed)
    catalog = bundle.catalog
    categories = sorted(catalog["category_id"].unique())
    category_weights = (
        catalog.groupby("category_id").size().reindex(categories).fillna(1).to_numpy(dtype=float)
    )
    category_weights = category_weights / category_weights.sum()
    medians = catalog.groupby("category_id")["price"].median().to_dict()

    missions: list[Mission] = []
    for _idx in range(n_missions):
        n_required = int(rng.integers(1, 4))
        required = list(rng.choice(categories, size=n_required, replace=False, p=category_weights))
        optional_pool = [category for category in categories if category not in required]
        optional = []
        if optional_pool and rng.random() < 0.45:
            optional = [str(rng.choice(optional_pool))]

        median_total = sum(medians[category] for category in required)
        factor = float(rng.choice([0.55, 0.85, 1.05, 1.35, 1.7], p=[0.12, 0.2, 0.28, 0.25, 0.15]))
        max_budget = max(20_000.0, median_total * factor)
        max_merchants = int(rng.integers(1, 4))
        minimum_rating = float(rng.choice([4.0, 4.2, 4.4]))
        style = list(rng.choice(["minimalist", "sporty", "classic", "playful", "natural"], size=1))
        colors = list(rng.choice(["black", "white", "gray", "navy", "cream", "green"], size=2, replace=False))
        missions.append(Mission(
            goal="Evaluation mission: prepare " + ", ".join(required),
            required_categories=required,
            optional_categories=optional,
            max_budget=float(round(max_budget / 500) * 500),
            max_merchants=max_merchants,
            preferences=Preferences(
                style=style,
                colors=colors,
                minimum_rating=minimum_rating,
            ),
        ))
    return missions


class OfflineEvaluator:
    def __init__(self, bundle: DatasetBundle, ranker: HybridRanker, k: int = 10) -> None:
        self.bundle = bundle
        self.ranker = ranker
        self.k = k
        self.catalog_service = CatalogService().load_from_bundle(bundle)
        self.catalog = self.catalog_service.catalog

        positives_train = bundle.train[bundle.train["event_type"].isin(POSITIVE_EVENTS)]
        self.train_events = positives_train.sort_values(
            ["user_id", "event_timestamp", "event_id"]
        ).reset_index(drop=True)
        event_weights = settings.get("features.event_weights", {})
        self.history_weights: dict[str, dict[str, float]] = {}
        for row in positives_train.itertuples():
            bucket = self.history_weights.setdefault(row.user_id, {})
            bucket[row.product_id] = bucket.get(row.product_id, 0.0) + float(
                event_weights.get(row.event_type, 1.0) or 1.0
            )
        self.train_seen = positives_train.groupby("user_id")["product_id"].agg(set).to_dict()
        self.train_counts = positives_train.groupby("user_id")["product_id"].nunique().to_dict()
        positives_test = bundle.test[bundle.test["event_type"].isin(POSITIVE_EVENTS)]
        relevant = {
            user_id: set(group["product_id"]) - self.train_seen.get(user_id, set())
            for user_id, group in positives_test.groupby("user_id")
        }
        self.relevant = {user_id: items for user_id, items in relevant.items() if items}
        self.product_categories = dict(
            zip(self.catalog["product_id"], self.catalog["category_id"], strict=False)
        )
        self.users = {row["user_id"]: row for row in bundle.users.to_dict("records")}
        self.mission_cache: dict[str, Mission] = {}
        self.catalog_size = int(self.catalog["product_id"].nunique())
        self.popularity_counts = ranker.popularity.global_counts
        self.long_tail_threshold = float(
            np.median([self.popularity_counts.get(pid, 0) for pid in self.catalog["product_id"]])
        )

    def _mission_for(self, user_id: str) -> Mission:
        if user_id not in self.mission_cache:
            self.mission_cache[user_id] = simulate_mission_for_user(
                pd.Series(self.users[user_id]), self.catalog
            )
        return self.mission_cache[user_id]

    def _relevant_for(self, user_id: str, mission: Mission) -> set[str]:
        categories = set(mission.all_categories)
        return {
            product_id for product_id in self.relevant.get(user_id, set())
            if self.product_categories.get(product_id) in categories
        }

    def _evaluate_ranking_with(
        self,
        ranker: HybridRanker,
        *,
        user_ids: list[str] | None = None,
        k: int | None = None,
    ) -> dict[str, Any]:
        k = k or self.k
        targets = user_ids or sorted(self.relevant)
        metric_rows: list[dict[str, float]] = []
        cold_rows: list[dict[str, float]] = []
        recommendations: dict[str, list[str]] = {}
        latencies: list[float] = []
        for user_id in targets:
            mission = self._mission_for(user_id)
            relevant = self._relevant_for(user_id, mission)
            if not relevant:
                continue
            start = time.perf_counter()
            result = ranker.rank(
                self.catalog,
                mission,
                user_id=user_id,
                history_weights=self.history_weights.get(user_id),
                strategy="hybrid_mission",
                top_k=k,
                exclude_product_ids=self.train_seen.get(user_id, set()),
            )
            latencies.append((time.perf_counter() - start) * 1000.0)
            recommended = [item.product_id for item in result.items]
            recommendations[user_id] = recommended
            metrics = evaluate_recommendation(recommended, relevant, k=k)
            metric_rows.append(metrics)
            if self.train_counts.get(user_id, 0) <= 5:
                cold_rows.append(metrics)

        aggregated = aggregate_metrics(metric_rows, [f"{name.split('@')[0]}@{k}" if "@" in name else name for name in METRIC_NAMES])
        catalog_metrics = summarize_catalog_metrics(
            recommendations,
            content=ranker.content,
            popularity_counts=self.popularity_counts,
            n_interactions=max(1, ranker.popularity.total),
            catalog_size=self.catalog_size,
            long_tail_threshold=self.long_tail_threshold,
        )
        ndcg_values = [row[f"ndcg@{k}"] for row in metric_rows]
        recall_values = [row[f"recall@{k}"] for row in metric_rows]
        return {
            "metrics": aggregated,
            "ndcg_confidence_interval": bootstrap_ci(ndcg_values, seed=settings.seed),
            "recall_confidence_interval": bootstrap_ci(recall_values, seed=settings.seed),
            "n_users": len(metric_rows),
            "n_cold_start_users": len(cold_rows),
            "cold_start_metrics": aggregate_metrics(cold_rows) if cold_rows else {},
            "catalog_metrics": catalog_metrics,
            "latency_ms": {
                "mean": round(float(np.mean(latencies)), 2) if latencies else 0.0,
                "p95": round(float(np.percentile(latencies, 95)), 2) if latencies else 0.0,
            },
            "ndcg_per_user": [round(float(value), 6) for value in ndcg_values],
        }

    # ------------------------------------------------------------------
    def evaluate_cold_start(self, n_users: int = 60, seed: int | None = None) -> dict[str, Any]:
        """Simulate cold start by hiding most interaction history.

        Compare full history, the final two items as anonymous session context,
        and no history for the same users. This is an offline simulation, not a
        measurement of genuinely new users.
        """
        rng = np.random.default_rng(settings.seed if seed is None else seed)
        eligible = [user_id for user_id in sorted(self.relevant) if self.train_counts.get(user_id, 0) >= 8]
        if len(eligible) < 10:
            return {"status": "insufficient_sample", "eligible_users": len(eligible)}
        sample = [
            str(user_id)
            for user_id in rng.choice(eligible, size=min(n_users, len(eligible)), replace=False)
        ]
        event_weights = settings.get("features.event_weights", {})

        results: dict[str, Any] = {}
        for scenario in ("known_user", "session_2_items", "no_history"):
            rows: list[dict[str, float]] = []
            for user_id in sample:
                mission = self._mission_for(user_id)
                relevant = self._relevant_for(user_id, mission)
                if not relevant:
                    continue
                history_weights: dict[str, float] = {}
                if scenario == "session_2_items":
                    tail = self.train_events[self.train_events["user_id"] == user_id].tail(2)
                    for row in tail.itertuples():
                        history_weights[row.product_id] = history_weights.get(row.product_id, 0.0) + float(
                            event_weights.get(row.event_type, 1.0) or 1.0
                        )
                result = self.ranker.rank(
                    self.catalog,
                    mission,
                    user_id=user_id if scenario == "known_user" else None,
                    session_weights=history_weights or None,
                    history_weights=(
                        self.history_weights.get(user_id) if scenario == "known_user" else None
                    ),
                    strategy="hybrid_mission",
                    top_k=self.k,
                    exclude_product_ids=self.train_seen.get(user_id, set()),
                )
                rows.append(
                    evaluate_recommendation(
                        [item.product_id for item in result.items], relevant, k=self.k
                    )
                )
            results[scenario] = {
                **aggregate_metrics(rows),
                "n_users": len(rows),
                "context": {
                    "known_user": "complete profile from training data",
                    "session_2_items": "the final two interactions as anonymous session context",
                    "no_history": "no history; mission, content, and popularity only",
                }[scenario],
            }
        return {
            "status": "simulation",
            "scenarios": results,
            "n_users": len(sample),
            "note": (
                "Cold start is simulated by hiding history for the same users; this does not "
                "represent real new users or production performance."
            ),
        }

    # ------------------------------------------------------------------
    def _basket_for_strategy(
        self,
        mission: Mission,
        strategy: str,
        mode: str,
        scored_cache: dict[str, pd.DataFrame],
    ) -> BasketResult:
        if strategy not in scored_cache:
            result = self.ranker.rank(self.catalog, mission, strategy=strategy, top_k=self.k)
            scored_cache[strategy] = result.scored
        scored = scored_cache[strategy]
        if mode == "independent":
            return naive_independent_basket(scored, mission)
        return optimize_basket(scored, mission, self.catalog)

    def evaluate_baskets(self, missions: list[Mission]) -> dict[str, Any]:
        configurations = {
            "EXP-002": ("popularity_category", "independent", "Category-popularity baseline without optimization"),
            "EXP-006": ("hybrid_mission", "independent", "Hybrid plus mission without basket optimization"),
            "EXP-007": ("hybrid_mission", "optimized", "Hybrid + basket optimization (ILP)"),
            "EXP-008": ("hybrid_exposure", "optimized", "Hybrid + controlled exposure + optimization"),
        }
        results: dict[str, list[BasketResult]] = defaultdict(list)
        scored_caches: list[dict[str, pd.DataFrame]] = []
        for mission in missions:
            cache: dict[str, pd.DataFrame] = {}
            for key, (strategy, mode, _) in configurations.items():
                results[key].append(self._basket_for_strategy(mission, strategy, mode, cache))
            scored_caches.append(cache)

        substitution_success = self._substitution_success(missions, scored_caches, limit=25)
        summaries: dict[str, Any] = {}
        for key, (strategy, mode, label) in configurations.items():
            summary = summarize_baskets(
                results[key],
                substitution_success=substitution_success if key == "EXP-007" else None,
            )
            summary.update({
                "label": label,
                "strategy": strategy,
                "basket_mode": mode,
                "evaluated_missions": len(missions),
            })
            summaries[key] = summary
        return summaries

    def _substitution_success(
        self,
        missions: list[Mission],
        scored_caches: list[dict[str, pd.DataFrame]],
        limit: int = 25,
    ) -> float | None:
        successes = 0
        attempts = 0
        for mission, cache in list(zip(missions, scored_caches, strict=False))[:limit]:
            scored = cache.get("hybrid_mission")
            if scored is None or scored.empty:
                continue
            primary = optimize_basket(scored, mission, self.catalog)
            if not primary.feasible:
                continue
            for item in primary.items[:3]:
                reduced = scored[scored["product_id"] != item.product_id]
                replacement = optimize_basket(reduced, mission, self.catalog)
                attempts += 1
                if replacement.feasible and replacement.total_price <= mission.max_budget:
                    successes += 1
        return successes / attempts if attempts else None

    # ------------------------------------------------------------------
    def _ablation(self, ranking_results: dict[str, Any], basket_results: dict[str, Any]) -> dict[str, Any]:
        base_config = copy.deepcopy(self.ranker.config)
        base_weights = dict(self.ranker.weights)
        variants = {
            "no_collaborative_signal": {"collaborative": 0.0},
            "no_content_signal": {"content": 0.0},
            "no_mission_signal": {"mission": 0.0},
            "no_quality_signal": {"quality": 0.0},
            "no_affinity_signal": {"affinity": 0.0},
        }
        subset_users = sorted(self.relevant)[:180]
        results: dict[str, Any] = {}
        base_subset = self._evaluate_ranking_with(self.ranker, user_ids=subset_users)
        results["base_all_signals"] = {
            "metrics": base_subset["metrics"],
            "weights": base_weights,
            "note": f"Full configuration on a subset of {len(subset_users)} test users.",
        }
        for name, override in variants.items():
            weights = dict(base_weights)
            weights.update(override)
            if sum(weights.values()) <= 0:
                continue
            config = copy.deepcopy(base_config)
            # Other weights are not renormalized: the ablation measures
            # a component's marginal contribution, not an optimized alternative configuration.
            config["weights"] = weights
            ranker = HybridRanker(
                self.ranker.content, self.ranker.collaborative, self.ranker.popularity, config=config
            )
            results[name] = self._evaluate_ranking_with(ranker, user_ids=subset_users)
            results[name]["weights"] = config["weights"]
            note = f"Ablation on a subset of {len(subset_users)} test users."
            zeroed = [key for key, value in override.items() if value == 0.0 and base_weights.get(key, 0.0) == 0.0]
            if zeroed:
                note += (
                    f" Components {', '.join(zeroed)} are already zero in the selected configuration, "
                    "so this variant is identical to the baseline."
                )
            results[name]["note"] = note

        results["no_exposure_adjustment"] = {
            "with_exposure": ranking_results.get("EXP-008", {}).get("metrics"),
            "without_exposure": ranking_results.get("EXP-006", {}).get("metrics"),
            "coverage_with_exposure": ranking_results.get("EXP-008", {}).get("catalog_metrics", {}).get("catalog_coverage"),
            "coverage_without_exposure": ranking_results.get("EXP-006", {}).get("catalog_metrics", {}).get("catalog_coverage"),
            "note": "Controlled exposure is compared under the same hybrid-mission configuration.",
        }
        results["no_basket_constraints"] = {
            "with_constraints": basket_results.get("EXP-007"),
            "without_constraints": basket_results.get("EXP-006"),
            "note": "Without hard constraints, the system selects the top product per category without checking total budget or merchant count.",
        }
        return results

    def _ab_simulation(self, ranking_results: dict[str, Any]) -> dict[str, Any]:
        control = ranking_results.get("EXP-005", {}).get("ndcg_per_user") or []
        treatment = ranking_results.get("EXP-006", {}).get("ndcg_per_user") or []
        n = min(len(control), len(treatment))
        if n < 10:
            return {"status": "insufficient_sample"}
        rng = np.random.default_rng(settings.seed)
        differences = []
        for _ in range(1000):
            indices = rng.integers(0, n, size=n)
            differences.append(float(np.mean(np.asarray(treatment)[indices]) - np.mean(np.asarray(control)[indices])))
        return {
            "status": "simulation_only",
            "experiment_id": "AB-001",
            "unit": "simulated_user",
            "n_per_group": n,
            "control_mean_ndcg": float(np.mean(control[:n])),
            "treatment_mean_ndcg": float(np.mean(treatment[:n])),
            "absolute_lift": float(np.mean(treatment[:n]) - np.mean(control[:n])),
            "bootstrap_95_ci": [
                float(np.quantile(differences, 0.025)),
                float(np.quantile(differences, 0.975)),
            ],
            "label": (
                "OFFLINE SIMULATION. Assignment is not randomized across live sessions and does not establish causality."
            ),
        }

    def run(self, basket_missions: int | None = None) -> dict[str, Any]:
        n_missions = int(basket_missions or settings.get("evaluation.n_basket_missions", 120))
        ranking_results: dict[str, Any] = {}
        for experiment_id, (name, strategy, scope) in EXPERIMENT_STRATEGIES.items():
            if scope == "basket":
                continue
            started = time.perf_counter()
            result = self._evaluate_strategy(strategy)
            result.update({
                "experiment_id": experiment_id,
                "name": name,
                "strategy": strategy,
                "status": "completed",
                "evaluation_scope": scope,
                "runtime_seconds": round(time.perf_counter() - started, 1),
            })
            ranking_results[experiment_id] = result
            print(
                f"[ranking] {experiment_id} {name}: "
                f"NDCG@10={result['metrics'].get('ndcg@10', 0):.4f}, "
                f"Recall@10={result['metrics'].get('recall@10', 0):.4f}"
            )

        print("[basket] running basket evaluation...")
        missions = generate_evaluation_missions(self.bundle, n_missions=n_missions, seed=settings.seed)
        basket_results = self.evaluate_baskets(missions)
        for key, summary in basket_results.items():
            print(
                f"[basket] {key}: feasibility={summary.get('budget_feasibility_rate')}, "
                f"coverage={summary.get('required_category_coverage')}"
            )

        print("[ablation] running the ablation study...")
        ablation = self._ablation(ranking_results, basket_results)
        ab_simulation = self._ab_simulation(ranking_results)
        print("[cold-start] running the cold-start simulation...")
        cold_start = self.evaluate_cold_start()

        weights_config = read_json(settings.models_dir / "hybrid_config.json", {}) or {}
        payload = {
            "generated_at": iso_now(),
            "dataset_version": settings.dataset.version,
            "model_version": settings.model_version,
            "seed": settings.seed,
            "k": self.k,
            "test_set": {
                "type": "temporal_holdout_per_user",
                "n_users": len(self.relevant),
                "n_events": int(len(self.bundle.test)),
                "relevance_definition": (
                    "Products with positive events in the temporal holdout after excluding "
                    "products already seen in training."
                ),
                "n_catalog_items": self.catalog_size,
            },
            "weights": weights_config.get("weights") or self.ranker.weights,
            "ranking": ranking_results,
            "baskets": basket_results,
            "ablation": ablation,
            "ab_simulation": ab_simulation,
            "cold_start_simulation": cold_start,
            "notes": [
                "All data is synthetic; the values do not represent a real marketplace.",
                "Ranking metrics use a per-user temporal holdout.",
                "EXP-007 uses basket metrics because its objective is combination optimization.",
                "Confidence intervals use user-level bootstrapping.",
                "The A/B simulation is not an online experiment and must not be presented as causal evidence.",
            ],
        }
        write_json(settings.reports_dir / "evaluation.json", payload)
        self._write_experiments(payload)
        self._write_benchmark(payload)
        return payload

    def _evaluate_strategy(self, strategy: str) -> dict[str, Any]:
        base = self.ranker
        config = copy.deepcopy(base.config)
        config["weights"] = dict(base.weights)
        ranker = HybridRanker(base.content, base.collaborative, base.popularity, config=config)

        metric_rows: list[dict[str, float]] = []
        cold_rows: list[dict[str, float]] = []
        recommendations: dict[str, list[str]] = {}
        latencies: list[float] = []
        for user_id in sorted(self.relevant):
            mission = self._mission_for(user_id)
            relevant = self._relevant_for(user_id, mission)
            if not relevant:
                continue
            start = time.perf_counter()
            result = ranker.rank(
                self.catalog,
                mission,
                user_id=user_id,
                history_weights=self.history_weights.get(user_id),
                strategy=strategy,
                top_k=self.k,
                exclude_product_ids=self.train_seen.get(user_id, set()),
            )
            latencies.append((time.perf_counter() - start) * 1000.0)
            recommended = [item.product_id for item in result.items]
            recommendations[user_id] = recommended
            metrics = evaluate_recommendation(recommended, relevant, k=self.k)
            metric_rows.append(metrics)
            if self.train_counts.get(user_id, 0) <= 5:
                cold_rows.append(metrics)
        aggregated = aggregate_metrics(metric_rows, METRIC_NAMES)
        catalog_metrics = summarize_catalog_metrics(
            recommendations,
            content=ranker.content,
            popularity_counts=self.popularity_counts,
            n_interactions=max(1, ranker.popularity.total),
            catalog_size=self.catalog_size,
            long_tail_threshold=self.long_tail_threshold,
        )
        ndcg_values = [row["ndcg@10"] for row in metric_rows]
        return {
            "metrics": aggregated,
            "ndcg_confidence_interval": bootstrap_ci(ndcg_values, seed=settings.seed),
            "n_users": len(metric_rows),
            "n_cold_start_users": len(cold_rows),
            "cold_start_metrics": aggregate_metrics(cold_rows) if cold_rows else {},
            "catalog_metrics": catalog_metrics,
            "latency_ms": {
                "mean": round(float(np.mean(latencies)), 2) if latencies else 0.0,
                "p95": round(float(np.percentile(latencies, 95)), 2) if latencies else 0.0,
            },
            "ndcg_per_user": [round(float(value), 6) for value in ndcg_values],
        }

    # ------------------------------------------------------------------
    def _write_experiments(self, payload: dict[str, Any]) -> None:
        experiments: dict[str, Any] = {}
        for experiment_id, (name, strategy, scope) in EXPERIMENT_STRATEGIES.items():
            entry: dict[str, Any] = {
                "experiment_id": experiment_id,
                "name": name,
                "model": strategy,
                "strategy": strategy,
                "scope": scope,
                "status": "completed",
            }
            if experiment_id in payload["ranking"]:
                entry["ranking_metrics"] = payload["ranking"][experiment_id]["metrics"]
                entry["catalog_metrics"] = payload["ranking"][experiment_id]["catalog_metrics"]
                entry["n_users"] = payload["ranking"][experiment_id]["n_users"]
            if experiment_id in payload["baskets"]:
                entry["basket_metrics"] = payload["baskets"][experiment_id]
            experiments[experiment_id] = entry
        write_json(settings.reports_dir / "experiments.json", {
            "generated_at": payload["generated_at"],
            "dataset_version": payload["dataset_version"],
            "model_version": payload["model_version"],
            "seed": payload["seed"],
            "results": experiments,
            "ab_simulation": payload["ab_simulation"],
            "note": "Offline results; not evidence of real business impact.",
        })

    def _write_benchmark(self, payload: dict[str, Any]) -> None:
        lines = [
            "# Benchmark Report : RASA",
            "",
            f"- Generated: {payload['generated_at']}",
            f"- Dataset: `{payload['dataset_version']}` (synthetic)",
            f"- Model: `{payload['model_version']}`",
            f"- Seed: {payload['seed']}",
            f"- Holdout: {payload['test_set']['n_users']} users, {payload['test_set']['n_events']} events",
            f"- Relevance definition: {payload['test_set']['relevance_definition']}",
            "",
            "## 1. Ranking (k = 10)",
            "",
            "| Exp | Model | NDCG@10 | Recall@10 | Precision@10 | MAP@10 | MRR | HitRate@10 | NDCG 95% CI |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
        for experiment_id, result in payload["ranking"].items():
            metrics = result.get("metrics", {})
            ci = result.get("ndcg_confidence_interval") or {}
            lines.append(
                f"| {experiment_id} | {result['name']} | {metrics.get('ndcg@10', 0):.4f} | "
                f"{metrics.get('recall@10', 0):.4f} | {metrics.get('precision@10', 0):.4f} | "
                f"{metrics.get('map@10', 0):.4f} | {metrics.get('mrr', 0):.4f} | "
                f"{metrics.get('hit_rate@10', 0):.4f} | "
                f"[{ci.get('ci_low', 0):.4f}, {ci.get('ci_high', 0):.4f}] |"
            )
        lines.extend([
            "",
            "## 2. Basket",
            "",
            "| Exp | Configuration | Feasibility | Required coverage | Avg merchant | Budget utilization | Basket relevance |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
        ])
        for experiment_id, result in payload["baskets"].items():
            lines.append(
                f"| {experiment_id} | {result['label']} | "
                f"{result.get('budget_feasibility_rate', 0):.4f} | "
                f"{result.get('required_category_coverage', 0):.4f} | "
                f"{result.get('avg_merchant_count', 0)} | "
                f"{result.get('budget_utilization', 0):.4f} | "
                f"{result.get('basket_relevance', 0):.4f} |"
            )
        lines.extend([
            "",
            "## 3. Ablation",
            "",
            "| Variant | NDCG@10 | Recall@10 |",
            "| --- | ---: | ---: |",
        ])
        for name, result in payload["ablation"].items():
            metrics = result.get("metrics", {}) if isinstance(result, dict) else {}
            if metrics:
                lines.append(
                    f"| {name} | {metrics.get('ndcg@10', 0):.4f} | {metrics.get('recall@10', 0):.4f} |"
                )
            else:
                lines.append(f"| {name} | - | - |")
        lines.extend([
            "",
            "## 4. Cold-Start Simulation",
            "",
            "| Scenario | NDCG@10 | Recall@10 | HitRate@10 | Users |",
            "| --- | ---: | ---: | ---: | ---: |",
        ])
        cold = payload.get("cold_start_simulation", {}) or {}
        for scenario, result in (cold.get("scenarios") or {}).items():
            lines.append(
                f"| {scenario} | {result.get('ndcg@10', 0):.4f} | {result.get('recall@10', 0):.4f} | "
                f"{result.get('hit_rate@10', 0):.4f} | {result.get('n_users', 0)} |"
            )
        lines.extend([
            "",
            "## 5. A/B Simulation",
            "",
            f"- Status: **{payload['ab_simulation'].get('status')}**",
            f"- Absolute lift (simulation): {payload['ab_simulation'].get('absolute_lift')}",
            f"- Note: {payload['ab_simulation'].get('label')}",
            "",
            "## 6. Limitations",
            "",
        ])
        lines.extend(f"- {note}" for note in payload["notes"])
        output = settings.reports_dir / "benchmark-report.md"
        output.write_text("\n".join(lines) + "\n", encoding="utf-8")
        docs_output = settings.root_dir / "docs" / "reports" / "benchmark-report.md"
        docs_output.parent.mkdir(parents=True, exist_ok=True)
        docs_output.write_text("\n".join(lines) + "\n", encoding="utf-8")
