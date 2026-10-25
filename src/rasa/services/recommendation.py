"""End-to-end recommendation orchestrator with audit persistence."""

from __future__ import annotations

import time
import uuid
from dataclasses import replace
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from rasa.config import settings
from rasa.db.models import (
    BasketItem as BasketItemRow,
)
from rasa.db.models import (
    BasketSolution,
    ExperimentAssignment,
    ExperimentDefinition,
    InteractionEvent,
    RecommendationRequest,
)
from rasa.db.models import (
    RecommendationItem as RecommendationItemRow,
)
from rasa.explanations.generator import build_basket_explanations, build_tradeoffs
from rasa.missions.validation import Mission
from rasa.optimization.basket import BasketResult, naive_independent_basket, optimize_basket
from rasa.ranking.ranker import HybridRanker, RankResult
from rasa.services.feedback import POSITIVE_TYPES, session_weights
from rasa.services.missions import create_mission, ensure_session
from rasa.utils import clamp, iso_now, json_safe, stable_hash, utcnow


class RecommendationService:
    def __init__(self, ranker: HybridRanker, model_version: str) -> None:
        self.ranker = ranker
        self.model_version = model_version

    # ------------------------------------------------------------------
    def _history_weights(self, session: Session, user_id: str | None) -> dict[str, float]:
        if not user_id:
            return {}
        event_weights = settings.get("features.event_weights", {})
        rows = list(
            session.scalars(
                select(InteractionEvent)
                .where(
                    InteractionEvent.user_id == user_id,
                    InteractionEvent.event_type.in_(POSITIVE_TYPES),
                )
                .order_by(InteractionEvent.event_timestamp.desc())
                .limit(60)
            )
        )
        result: dict[str, float] = {}
        for row in rows:
            if not row.product_id:
                continue
            result[row.product_id] = result.get(row.product_id, 0.0) + float(
                event_weights.get(row.event_type, 1.0) or 1.0
            )
        return result

    def _assign_experiment(
        self,
        session: Session,
        session_id: str,
        experiment_id: str | None,
        default_strategy: str,
    ) -> tuple[str, dict[str, Any] | None]:
        if not experiment_id:
            return default_strategy, None
        definition = session.get(ExperimentDefinition, experiment_id)
        if definition is None:
            return default_strategy, None
        variants = (definition.config or {}).get("variants", {})
        if not variants:
            return default_strategy, None
        existing = session.scalar(
            select(ExperimentAssignment).where(
                ExperimentAssignment.session_id == session_id,
                ExperimentAssignment.experiment_id == experiment_id,
            )
        )
        if existing is not None:
            variant = existing.variant
        else:
            bucket = int(stable_hash(session_id, experiment_id)[:8], 16) % 2
            variant = list(variants.keys())[bucket]
            session.add(ExperimentAssignment(
                session_id=session_id,
                experiment_id=experiment_id,
                variant=variant,
                assigned_at=utcnow(),
            ))
            session.flush()
        strategy = str(variants.get(variant, default_strategy))
        return strategy, {
            "experiment_id": experiment_id,
            "variant": variant,
            "strategy": strategy,
            "label": "A/B simulation, not causal evidence",
        }

    # ------------------------------------------------------------------
    def _alternative_products(
        self,
        scored: pd.DataFrame,
        selected_ids: set[str],
        limit: int = 2,
    ) -> dict[str, list[dict[str, Any]]]:
        result: dict[str, list[dict[str, Any]]] = {}
        for category_id, group in scored.groupby("category_id"):
            options = group[~group["product_id"].isin(selected_ids)].nlargest(limit, "score")
            result[str(category_id)] = [
                {
                    "product_id": str(row["product_id"]),
                    "product_name": str(row["product_name"]),
                    "price": float(row["price"]),
                    "rating": float(row["rating"]),
                    "merchant_id": str(row["merchant_id"]),
                    "merchant_name": str(row.get("merchant_name", row["merchant_id"])),
                    "score": round(float(row["score"]), 6),
                    "availability_status": str(row["availability_status"]),
                }
                for _, row in options.iterrows()
            ]
        return result

    def _alternative_baskets(
        self,
        scored: pd.DataFrame,
        mission: Mission,
        catalog: pd.DataFrame,
        primary: BasketResult,
        diagnostics: dict[str, Any],
    ) -> list[dict[str, Any]]:
        variants: list[tuple[str, str, Mission]] = []
        if mission.max_merchants < 10:
            variants.append((
                "merchant_luwes",
                "Alternative with a relaxed merchant limit",
                replace(mission, max_merchants=mission.max_merchants + 1),
            ))
        variants.append((
            "anggaran_luwes",
            "Alternative with a 15% higher budget",
            replace(mission, max_budget=mission.max_budget * 1.15, max_merchants=mission.max_merchants + 1),
        ))

        alternatives: list[dict[str, Any]] = []
        seen: set[tuple[str, ...]] = {tuple(sorted(item.product_id for item in primary.items))}
        for key, label, variant_mission in variants:
            result = optimize_basket(scored, variant_mission, catalog, diagnostics)
            if not result.feasible:
                continue
            signature = tuple(sorted(item.product_id for item in result.items))
            if signature in seen:
                continue
            seen.add(signature)
            explanations = build_basket_explanations(result.to_dict(), variant_mission, result.diagnostics)
            alternatives.append({
                "alternative_id": key,
                "label": label,
                "basket": result.to_dict(),
                "explanations": explanations,
                "tradeoffs": build_tradeoffs(primary.to_dict(), result.to_dict()),
            })
            if len(alternatives) >= 2:
                break
        return alternatives

    # ------------------------------------------------------------------
    def recommend(
        self,
        session: Session,
        *,
        mission: Mission,
        session_id: str,
        strategy: str = "hybrid_mission",
        user_id: str | None = None,
        top_k: int | None = None,
        include_comparison: bool = False,
        experiment_id: str | None = None,
        persist: bool = True,
        mission_id: str | None = None,
        search_text: str | None = None,
    ) -> dict[str, Any]:
        start = time.perf_counter()
        catalog_service_frame = self._catalog_frame(session)
        strategy, assignment = self._assign_experiment(session, session_id, experiment_id, strategy)
        session_profile = session_weights(session, session_id)
        history = self._history_weights(session, user_id) if user_id else {}

        rank_result: RankResult = self.ranker.rank(
            catalog_service_frame,
            mission,
            user_id=user_id,
            session_weights=session_profile,
            history_weights=history,
            strategy=strategy,
            top_k=top_k,
            search_text=search_text,
        )

        if persist:
            ensure_session(session, session_id, experiment_variant=assignment["variant"] if assignment else None)
            if mission_id is None:
                stored_mission = create_mission(
                    session, mission, session_id=session_id,
                    warnings=[], status="used_for_recommendation",
                )
                mission_id = stored_mission.mission_id

        basket = optimize_basket(
            rank_result.scored,
            mission,
            catalog_service_frame,
            rank_result.diagnostics.get("candidate_generation", {}),
        )

        selected_ids = {item.product_id for item in basket.items}
        alternatives_by_category = self._alternative_products(rank_result.scored, selected_ids)

        recommendations = []
        for item in rank_result.items:
            payload = item.to_dict()
            payload["alternatives"] = alternatives_by_category.get(item.category_id, [])[:2]
            payload["alternatives"] = [
                alt for alt in payload["alternatives"] if alt["product_id"] != item.product_id
            ]
            payload["is_selected_in_basket"] = item.product_id in selected_ids
            recommendations.append(payload)

        # Alternative solutions run the optimizer again. Compute them only when
        # explicitly requested so the primary path stays within its latency budget.
        alternative_baskets = (
            self._alternative_baskets(
                rank_result.scored, mission, catalog_service_frame, basket, rank_result.diagnostics
            )
            if include_comparison
            else []
        )

        comparison = None
        if include_comparison:
            baseline = naive_independent_basket(rank_result.scored, mission)
            comparison = {
                "baseline": baseline.to_dict(),
                "optimized": basket.to_dict(),
                "deltas": {
                    "total_price": float(basket.total_price - baseline.total_price),
                    "merchant_count": int(basket.merchant_count - baseline.merchant_count),
                    "required_category_coverage": float(
                        basket.required_category_coverage - baseline.required_category_coverage
                    ),
                    "feasibility_changed": bool(basket.feasible != baseline.feasible),
                },
                "label": "The baseline selects the top product in each category without joint optimization.",
            }

        latency_ms = (time.perf_counter() - start) * 1000.0
        status = "success" if basket.feasible else "infeasible"
        limitations = [
            "Prices, inventory, ratings, and merchants are simulated, not real-time data.",
            "This system is not a marketplace and does not process payments or orders.",
            "Internal relevance scores are not calibrated purchase probabilities.",
        ]
        if rank_result.diagnostics.get("cold_start", {}).get("is_cold_user"):
            limitations.append(
                "The user profile has insufficient history, so the recommendation falls back "
                "to mission preferences, content, and category popularity."
            )

        response: dict[str, Any] = {
            "request_id": None,
            "mission_id": mission_id,
            "session_id": session_id,
            "status": status,
            "model_version": self.model_version,
            "strategy": strategy,
            "experiment": assignment,
            "generated_at": iso_now(),
            "mission": {
                "goal": mission.goal,
                "required_categories": mission.required_categories,
                "optional_categories": mission.optional_categories,
                "max_budget": float(mission.max_budget),
                "max_merchants": int(mission.max_merchants),
                "preferences": mission.preferences.to_dict(),
            },
            "basket": basket.to_dict(),
            "recommendations": recommendations,
            "explanations": build_basket_explanations(
                basket.to_dict(), mission, {**basket.diagnostics, "solver": basket.solver}
            ),
            "alternatives": {
                "products": alternatives_by_category,
                "baskets": alternative_baskets,
            },
            "comparison": comparison,
            "tradeoffs": (
                build_tradeoffs(basket.to_dict(), alternative_baskets[0]["basket"])
                if alternative_baskets else []
            ),
            "limitations": limitations,
            "diagnostics": rank_result.diagnostics,
            "meta": {
                "latency_ms": round(latency_ms, 2),
                "data_mode": "synthetic",
                "notice": "All prices, inventory, merchants, and interactions are simulated.",
                "candidate_count": int(len(rank_result.scored)),
            },
        }
        response = json_safe(response)

        if persist:
            request_row = self._persist(
                session,
                response=response,
                mission_id=mission_id,
                session_id=session_id,
                strategy=strategy,
                latency_ms=latency_ms,
                candidate_count=int(len(rank_result.scored)),
            )
            response["request_id"] = request_row.request_id

        return response

    def _catalog_frame(self, session: Session) -> pd.DataFrame:
        from rasa.services.catalog import catalog_service

        if not catalog_service.loaded:
            catalog_service.load(session)
        return catalog_service.catalog

    # ------------------------------------------------------------------
    def _persist(
        self,
        session: Session,
        *,
        response: dict[str, Any],
        mission_id: str | None,
        session_id: str,
        strategy: str,
        latency_ms: float,
        candidate_count: int,
    ) -> RecommendationRequest:
        request_id = f"req_{uuid.uuid4().hex[:12]}"
        row = RecommendationRequest(
            request_id=request_id,
            mission_id=mission_id,
            session_id=session_id,
            model_version=self.model_version,
            strategy=strategy,
            status=response["status"],
            latency_ms=float(latency_ms),
            candidate_count=int(candidate_count),
            fallback_used=False,
            request_payload=response.get("mission"),
            response_snapshot=response,
            created_at=utcnow(),
        )
        session.add(row)
        session.flush()

        selected = {item["product_id"] for item in response["basket"].get("items", [])}
        for rank_position, item in enumerate(response["recommendations"], start=1):
            session.add(RecommendationItemRow(
                request_id=request_id,
                product_id=item["product_id"],
                rank_position=rank_position,
                score=float(item["score"]),
                component_scores=item.get("components", {}),
                explanation={"reasons": item.get("reasons", [])},
                selected_in_basket=item["product_id"] in selected,
            ))

        basket_payload = response["basket"]
        basket_row = BasketSolution(
            basket_id=f"bsk_{uuid.uuid4().hex[:12]}",
            request_id=request_id,
            mission_id=mission_id,
            status=basket_payload["status"],
            total_price=float(basket_payload["total_price"]),
            budget_remaining=float(basket_payload["budget_remaining"]),
            merchant_count=int(basket_payload["merchant_count"]),
            required_category_coverage=float(basket_payload["required_category_coverage"]),
            solver=str(basket_payload.get("solver", "none")),
            explanation={
                "explanations": response["explanations"],
                "suggestions": basket_payload.get("suggestions", []),
                "diagnostics": basket_payload.get("diagnostics", {}),
            },
            created_at=utcnow(),
        )
        session.add(basket_row)
        session.flush()
        for item in basket_payload.get("items", []):
            session.add(BasketItemRow(
                basket_id=basket_row.basket_id,
                product_id=item["product_id"],
                quantity=1,
                unit_price=float(item["price"]),
                role=item.get("role", "required"),
            ))
        response["basket"]["basket_id"] = basket_row.basket_id
        session.flush()
        return row


def latency_budget_seconds() -> float:
    return float(settings.get("api.recommendation_timeout_seconds", 2.5))


def score_confidence(score: float) -> float:
    """Internal display value only; not a purchase probability."""
    return clamp(score)
