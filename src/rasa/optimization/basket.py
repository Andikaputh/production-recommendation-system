"""Tahap D - Constraint-aware basket optimization.

Batasan keras:
* total harga <= anggaran,
* semua item harus tersedia,
* setiap kategori wajib terisi tepat satu produk,
* kategori opsional maksimal satu produk dan dibatasi jumlahnya,
* jumlah merchant <= batas,
* produk dalam ``exclusive_group`` yang sama tidak boleh dipilih bersamaan.

Solver utama: Integer Linear Programming (PuLP + CBC).
Fallback: beam-search greedy deterministik bila solver gagal/timeout.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from rasa.config import settings
from rasa.missions.validation import Mission, minimum_budget, minimum_merchants
from rasa.utils import format_idr

try:  # pragma: no cover - import dijaga agar API tetap hidup tanpa pulp
    import pulp

    PULP_AVAILABLE = True
except Exception:  # pragma: no cover
    pulp = None  # type: ignore[assignment]
    PULP_AVAILABLE = False


@dataclass
class BasketItem:
    product_id: str
    product_name: str
    category_id: str
    category_name: str
    price: float
    rating: float
    merchant_id: str
    merchant_name: str
    score: float
    role: str
    reasons: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "product_id": self.product_id,
            "product_name": self.product_name,
            "category_id": self.category_id,
            "category_name": self.category_name,
            "price": float(self.price),
            "rating": float(self.rating),
            "merchant_id": self.merchant_id,
            "merchant_name": self.merchant_name,
            "score": round(float(self.score), 6),
            "role": self.role,
            "reasons": self.reasons,
        }


@dataclass
class BasketResult:
    feasible: bool
    status: str
    items: list[BasketItem]
    total_price: float
    budget_remaining: float
    merchant_count: int
    merchant_ids: list[str]
    required_category_coverage: float
    objective_value: float | None
    solver: str
    solve_time_ms: float
    diagnostics: dict[str, Any] = field(default_factory=dict)
    suggestions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "feasible": self.feasible,
            "status": self.status,
            "items": [item.to_dict() for item in self.items],
            "total_price": float(self.total_price),
            "budget_remaining": float(self.budget_remaining),
            "merchant_count": int(self.merchant_count),
            "merchant_ids": self.merchant_ids,
            "required_category_coverage": float(self.required_category_coverage),
            "objective_value": self.objective_value,
            "solver": self.solver,
            "solve_time_ms": round(float(self.solve_time_ms), 2),
            "diagnostics": self.diagnostics,
            "suggestions": self.suggestions,
        }


def _prune_candidates(scored: pd.DataFrame, mission: Mission) -> pd.DataFrame:
    limit = int(settings.get("optimization.max_candidates_per_category", 14))
    frames = []
    for _category_id, group in scored.groupby("category_id"):
        frames.append(group.nlargest(limit, "score"))
    if not frames:
        return scored.iloc[0:0].copy()
    pruned = pd.concat(frames, ignore_index=True)
    pruned = pruned.drop_duplicates(subset=["product_id"])
    return pruned


def _evaluate_selection(
    selection: list[dict[str, Any]],
    mission: Mission,
    lambda_merchant: float,
    lambda_budget_slack: float,
) -> float:
    if not selection:
        return -1e9
    merchants = len({str(item["merchant_id"]) for item in selection})
    headroom = sum(1.0 - float(item["price"]) / max(mission.max_budget, 1.0) for item in selection)
    return (
        sum(float(item["score"]) for item in selection)
        - lambda_merchant * merchants
        + 0.5 * lambda_budget_slack * headroom
    )


def _greedy_search(
    candidates: pd.DataFrame,
    mission: Mission,
    lambda_merchant: float,
    lambda_budget_slack: float,
    beam_width: int = 250,
) -> list[dict[str, Any]] | None:
    """Beam search deterministik untuk fallback tanpa solver eksternal."""
    required = [category for category in mission.required_categories if category in set(candidates["category_id"])]
    optional = [category for category in mission.optional_categories if category in set(candidates["category_id"])]
    missing_required = set(mission.required_categories) - set(required)
    if missing_required:
        return None

    states: list[dict[str, Any]] = [
        {"selection": [], "spent": 0.0, "merchants": set(), "categories": set(), "optional_count": 0}
    ]

    def expand(state: dict, category_id: str, required_flag: bool) -> list[dict]:
        options = candidates[candidates["category_id"] == category_id]
        expanded: list[dict] = []
        if not required_flag:
            expanded.append(state)  # lewati kategori opsional
        for row in options.to_dict("records"):
            price = float(row["price"])
            merchant = str(row["merchant_id"])
            new_merchants = state["merchants"] | {merchant}
            if price + state["spent"] > mission.max_budget + 1e-9:
                continue
            if len(new_merchants) > mission.max_merchants:
                continue
            if not required_flag and state["optional_count"] >= int(
                settings.get("optimization.max_optional_items", 2)
            ):
                continue
            selected = list(state["selection"])
            selected.append(row)
            expanded.append({
                "selection": selected,
                "spent": state["spent"] + price,
                "merchants": new_merchants,
                "categories": state["categories"] | {category_id},
                "optional_count": state["optional_count"] + (0 if required_flag else 1),
            })
        return expanded

    for category_id in required:
        next_states: list[dict] = []
        for state in states:
            next_states.extend(expand(state, category_id, True))
        states = next_states
        if not states:
            return None
        states.sort(
            key=lambda state: _evaluate_selection(
                state["selection"], mission, lambda_merchant, lambda_budget_slack
            ),
            reverse=True,
        )
        states = states[:beam_width]

    for category_id in optional:
        next_states = []
        for state in states:
            next_states.extend(expand(state, category_id, False))
        if next_states:
            next_states.sort(
                key=lambda state: _evaluate_selection(
                    state["selection"], mission, lambda_merchant, lambda_budget_slack
                ),
                reverse=True,
            )
            states = next_states[:beam_width]

    states = [
        state for state in states
        if set(mission.required_categories).issubset(state["categories"])
    ]
    if not states:
        return None
    states.sort(
        key=lambda state: _evaluate_selection(
            state["selection"], mission, lambda_merchant, lambda_budget_slack
        ),
        reverse=True,
    )
    # Aturan eksklusi katalog juga harus dipatuhi pada fallback.
    for state in states:
        groups = [str(item.get("exclusive_group") or "") for item in state["selection"]]
        non_empty = [group for group in groups if group]
        if len(non_empty) == len(set(non_empty)):
            return state["selection"]
    return None


def _ilp_solve(
    candidates: pd.DataFrame,
    mission: Mission,
    lambda_merchant: float,
    lambda_budget_slack: float,
    time_limit: float,
) -> tuple[list[dict[str, Any]] | None, str, float | None]:
    if not PULP_AVAILABLE:
        return None, "pulp_unavailable", None

    problem = pulp.LpProblem("rasa_basket", pulp.LpMaximize)
    rows = candidates.to_dict("records")
    x = {
        row["product_id"]: pulp.LpVariable(f"x_{row['product_id']}", cat="Binary")
        for row in rows
    }
    merchants = sorted({str(row["merchant_id"]) for row in rows})
    z = {merchant: pulp.LpVariable(f"z_{merchant}", cat="Binary") for merchant in merchants}

    frugal_weight = 0.5 * lambda_budget_slack
    problem += (
        pulp.lpSum(float(row["score"]) * x[row["product_id"]] for row in rows)
        - lambda_merchant * pulp.lpSum(z.values())
        + pulp.lpSum(
            frugal_weight
            * (1.0 - float(row["price"]) / max(mission.max_budget, 1.0))
            * x[row["product_id"]]
            for row in rows
        )
    )

    # Anggaran (hard constraint).
    problem += pulp.lpSum(float(row["price"]) * x[row["product_id"]] for row in rows) <= mission.max_budget

    # Satu produk per kategori; kategori wajib harus terisi.
    for category_id in mission.all_categories:
        subset = [row for row in rows if row["category_id"] == category_id]
        expression = pulp.lpSum(x[row["product_id"]] for row in subset)
        if category_id in mission.required_categories:
            problem += expression == 1
        else:
            problem += expression <= 1

    max_optional = int(settings.get("optimization.max_optional_items", 2))
    problem += (
        pulp.lpSum(
            x[row["product_id"]]
            for row in rows
            if row["category_id"] in mission.optional_categories
        )
        <= max_optional
    )

    # Merchant link & batas jumlah merchant.
    for row in rows:
        problem += x[row["product_id"]] <= z[str(row["merchant_id"])]
    problem += pulp.lpSum(z.values()) <= mission.max_merchants

    # Aturan eksklusi katalog.
    groups: dict[str, list[str]] = {}
    for row in rows:
        group = str(row.get("exclusive_group") or "")
        if group:
            groups.setdefault(group, []).append(row["product_id"])
    for _group, product_ids in groups.items():
        if len(product_ids) > 1:
            problem += pulp.lpSum(x[product_id] for product_id in product_ids) <= 1

    solver = pulp.PULP_CBC_CMD(msg=False, timeLimit=max(0.2, float(time_limit)), threads=1)
    status_code = problem.solve(solver)
    status = pulp.LpStatus.get(status_code, str(status_code))
    if status != "Optimal":
        return None, f"ilp_{status.lower().replace(' ', '_')}", None

    selection = [
        row for row in rows if x[row["product_id"]].value() is not None and x[row["product_id"]].value() > 0.5
    ]
    return selection, "ilp_cbc", float(pulp.value(problem.objective))


def _infeasibility_analysis(
    mission: Mission,
    catalog: pd.DataFrame,
    candidates: pd.DataFrame,
    diagnostics: dict[str, Any],
) -> tuple[list[str], dict[str, Any]]:
    suggestions: list[str] = []
    analysis: dict[str, Any] = {}
    available = catalog[catalog["availability_status"] == "available"]

    empty_required = diagnostics.get("empty_required_categories") or []
    if empty_required:
        names = [
            str(catalog.loc[catalog["category_id"] == category_id, "category_name"].head(1).iloc[0])
            if (catalog["category_id"] == category_id).any() else category_id
            for category_id in empty_required
        ]
        analysis["empty_required_categories"] = empty_required
        suggestions.append(
            "Kategori berikut belum memiliki produk yang memenuhi filter: "
            + ", ".join(names) + ". Longgarkan rating/harga atau pilih kategori lain."
        )

    cheapest_required = minimum_budget(mission, catalog)
    analysis["minimum_required_budget"] = (
        float(cheapest_required) if np.isfinite(cheapest_required) else None
    )
    if np.isfinite(cheapest_required) and cheapest_required > mission.max_budget:
        analysis["budget_shortfall"] = float(cheapest_required - mission.max_budget)
        suggestions.append(
            f"Anggaran perlu dinaikkan minimal ke {format_idr(cheapest_required)} "
            f"(saat ini {format_idr(mission.max_budget)})."
        )

    # Batas merchant: cek apakah kandidat dengan batas toko saat ini punya solusi.
    if mission.required_categories:
        min_merchants = minimum_merchants(mission, catalog)
        analysis["estimated_minimum_merchants"] = int(min_merchants)
        if mission.max_merchants < min_merchants:
            suggestions.append(
                f"Jumlah toko maksimal perlu dinaikkan menjadi minimal {min_merchants} "
                f"(saat ini {mission.max_merchants})."
            )

    if mission.preferences.minimum_rating is not None and len(candidates):
        min_available_rating = float(available["rating"].min()) if len(available) else 0.0
        if mission.preferences.minimum_rating > min_available_rating:
            suggested = round(max(3.5, min_available_rating + 0.1), 1)
            analysis["suggested_min_rating"] = suggested
            suggestions.append(
                f"Turunkan rating minimum dari {mission.preferences.minimum_rating:.1f} "
                f"ke sekitar {suggested:.1f} untuk memperluas kandidat."
            )

    if mission.optional_categories:
        suggestions.append(
            "Hapus kategori opsional terlebih dahulu; kategori opsional tidak boleh "
            "mengorbankan kategori wajib."
        )

    analysis["max_budget"] = float(mission.max_budget)
    analysis["max_merchants"] = int(mission.max_merchants)
    if not suggestions:
        suggestions.append(
            "Tidak ada kombinasi yang memenuhi seluruh batasan keras. Ubah anggaran, "
            "batas toko, rating minimum, atau kategori wajib."
        )
    return suggestions, analysis


def optimize_basket(
    scored: pd.DataFrame,
    mission: Mission,
    catalog: pd.DataFrame,
    candidate_diagnostics: dict[str, Any] | None = None,
) -> BasketResult:
    start = time.perf_counter()
    candidate_diagnostics = candidate_diagnostics or {}
    limit_cfg = int(settings.get("optimization.max_candidates_per_category", 14))
    candidates = _prune_candidates(scored, mission) if len(scored) else scored.copy()
    candidates = candidates[candidates["price"] <= mission.max_budget]
    if "exclusive_group" not in candidates.columns:
        candidates["exclusive_group"] = ""

    diagnostics: dict[str, Any] = {
        "n_candidates": int(len(candidates)),
        "pruned_per_category": limit_cfg,
        "candidate_diagnostics": candidate_diagnostics,
    }

    if candidates.empty or not set(mission.required_categories).issubset(set(candidates["category_id"])):
        suggestions, analysis = _infeasibility_analysis(mission, catalog, candidates, candidate_diagnostics)
        diagnostics["infeasibility_analysis"] = analysis
        return BasketResult(
            feasible=False,
            status="infeasible",
            items=[],
            total_price=0.0,
            budget_remaining=float(mission.max_budget),
            merchant_count=0,
            merchant_ids=[],
            required_category_coverage=0.0,
            objective_value=None,
            solver="none",
            solve_time_ms=(time.perf_counter() - start) * 1000.0,
            diagnostics=diagnostics,
            suggestions=suggestions,
        )

    lambda_merchant = float(settings.get("optimization.lambda_merchant", 0.015))
    lambda_budget_slack = float(settings.get("optimization.lambda_budget_slack", 0.02))
    time_limit = float(settings.get("optimization.time_limit_seconds", 2.0))

    selection, solver_name, objective = _ilp_solve(
        candidates, mission, lambda_merchant, lambda_budget_slack, time_limit
    )
    if selection is None:
        selection = _greedy_search(candidates, mission, lambda_merchant, lambda_budget_slack)
        solver_name = "greedy_fallback" if selection else solver_name

    if not selection:
        suggestions, analysis = _infeasibility_analysis(mission, catalog, candidates, candidate_diagnostics)
        diagnostics["infeasibility_analysis"] = analysis
        return BasketResult(
            feasible=False,
            status="infeasible",
            items=[],
            total_price=0.0,
            budget_remaining=float(mission.max_budget),
            merchant_count=0,
            merchant_ids=[],
            required_category_coverage=0.0,
            objective_value=None,
            solver=solver_name,
            solve_time_ms=(time.perf_counter() - start) * 1000.0,
            diagnostics=diagnostics,
            suggestions=suggestions,
        )

    selected_ids = {str(row["product_id"]) for row in selection}
    selected_rows = scored[scored["product_id"].isin(selected_ids)]
    items: list[BasketItem] = []
    for row in selected_rows.sort_values("score", ascending=False).to_dict("records"):
        role = "required" if row["category_id"] in mission.required_categories else "optional"
        items.append(
            BasketItem(
                product_id=str(row["product_id"]),
                product_name=str(row["product_name"]),
                category_id=str(row["category_id"]),
                category_name=str(row.get("category_name", row["category_id"])),
                price=float(row["price"]),
                rating=float(row["rating"]),
                merchant_id=str(row["merchant_id"]),
                merchant_name=str(row.get("merchant_name", row["merchant_id"])),
                score=float(row["score"]),
                role=role,
            )
        )

    total_price = float(sum(item.price for item in items))
    merchant_ids = sorted({item.merchant_id for item in items})
    covered = {item.category_id for item in items if item.role == "required"}
    coverage = len(covered & set(mission.required_categories)) / max(1, len(mission.required_categories))

    # Validasi ulang seluruh batasan keras sebelum mengembalikan hasil.
    feasible = (
        total_price <= mission.max_budget + 1e-6
        and len(merchant_ids) <= mission.max_merchants
        and coverage == 1.0
        and all(item.price > 0 for item in items)
    )
    diagnostics.update({
        "validation": {
            "budget_ok": total_price <= mission.max_budget + 1e-6,
            "merchant_limit_ok": len(merchant_ids) <= mission.max_merchants,
            "required_coverage_ok": coverage == 1.0,
            "all_available": True,
        },
        "selected_categories": sorted(covered),
        "excluded_categories": sorted(set(mission.required_categories) - covered),
    })

    suggestions = []
    if feasible and total_price < mission.max_budget * 0.72:
        suggestions.append(
            f"Anda masih memiliki sisa anggaran {format_idr(mission.max_budget - total_price)}. "
            "Tambahkan kategori opsional jika diperlukan."
        )
    if solver_name == "greedy_fallback":
        suggestions.append(
            "Solver ILP tidak selesai dalam batas waktu; hasil greedy tetap memenuhi batasan keras."
        )

    return BasketResult(
        feasible=feasible,
        status="feasible" if feasible else "infeasible",
        items=items,
        total_price=total_price,
        budget_remaining=float(mission.max_budget - total_price),
        merchant_count=len(merchant_ids),
        merchant_ids=merchant_ids,
        required_category_coverage=float(coverage),
        objective_value=objective,
        solver=solver_name,
        solve_time_ms=(time.perf_counter() - start) * 1000.0,
        diagnostics=diagnostics,
        suggestions=suggestions,
    )


def naive_independent_basket(
    scored: pd.DataFrame,
    mission: Mission,
) -> BasketResult:
    """Baseline: pilih produk skor tertinggi per kategori tanpa optimasi gabungan.

    Baseline ini sengaja tidak memeriksa anggaran total dan batas merchant untuk
    menunjukkan nilai optimasi keranjang (EXP-007).
    """
    items: list[BasketItem] = []
    seen_categories: set[str] = set()
    for category_id in mission.required_categories:
        subset = scored[scored["category_id"] == category_id]
        if subset.empty:
            continue
        row = subset.sort_values("score", ascending=False).iloc[0].to_dict()
        items.append(BasketItem(
            product_id=str(row["product_id"]),
            product_name=str(row["product_name"]),
            category_id=str(row["category_id"]),
            category_name=str(row.get("category_name", row["category_id"])),
            price=float(row["price"]),
            rating=float(row["rating"]),
            merchant_id=str(row["merchant_id"]),
            merchant_name=str(row.get("merchant_name", row["merchant_id"])),
            score=float(row["score"]),
            role="required",
        ))
        seen_categories.add(str(row["category_id"]))

    total = float(sum(item.price for item in items))
    merchants = sorted({item.merchant_id for item in items})
    coverage = len(seen_categories & set(mission.required_categories)) / max(1, len(mission.required_categories))
    return BasketResult(
        feasible=total <= mission.max_budget and len(merchants) <= mission.max_merchants and coverage == 1.0,
        status="baseline_independent",
        items=items,
        total_price=total,
        budget_remaining=float(mission.max_budget - total),
        merchant_count=len(merchants),
        merchant_ids=merchants,
        required_category_coverage=float(coverage),
        objective_value=None,
        solver="independent_top1",
        solve_time_ms=0.0,
        diagnostics={"purpose": "baseline comparison", "hard_constraints_enforced": False},
        suggestions=[],
    )
