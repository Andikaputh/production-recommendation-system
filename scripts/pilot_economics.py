"""Editable illustrative SaaS economics; no claims about actual transactions."""
import argparse
import json
import math
from pathlib import Path


def calculate(a: dict) -> dict:
    keys = [k for k in a if k not in {"label", "currency"}]
    if any(not isinstance(a[k], (float, int)) or not math.isfinite(a[k]) or a[k] < 0 for k in keys):
        raise ValueError("Asumsi biaya harus angka nonnegatif dan finite.")
    if a["onboarding_amortization_months"] <= 0:
        raise ValueError("Bulan amortisasi harus positif.")
    onboarding = a["onboarding_hours"] * a["hourly_labor_cost"] / a["onboarding_amortization_months"]
    contribution = a["monthly_subscription"] - a["accepted_baskets_per_merchant_month"] * a["compute_cost_per_accepted_basket"] - a["support_hours_per_merchant_month"] * a["hourly_labor_cost"] - onboarding
    return {"label": a["label"], "monthly_contribution_per_merchant": round(contribution, 2),
            "break_even_merchants": math.ceil(a["fixed_monthly_cost"] / contribution) if contribution > 0 else None,
            "acquisition_payback_months": round(a["merchant_acquisition_cost"] / contribution, 2) if contribution > 0 else None,
            "actual_orders_revenue_margin": None}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=Path(__file__).resolve().parents[1] / "configs/pilot-economics.json")
    args = parser.parse_args()
    assumptions = json.loads(args.config.read_text(encoding="utf-8"))
    print(json.dumps({"base": calculate(assumptions), "sensitivity": {str(n): calculate({**assumptions, "accepted_baskets_per_merchant_month": n}) for n in [50, 100, 500]}}, indent=2))
