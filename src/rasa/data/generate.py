"""Generate RASA's fully synthetic catalog and interaction dataset.

The PRD permits transparently generated synthetic data when public datasets do
not include the merchant, inventory, price, and mission attributes required by
the product. A fixed seed makes relationships valid, excludes real personal
data, keeps relevance and cold-start cases controllable, and makes experiments
exactly reproducible. Outputs use auditable CSV and JSON files in ``data/raw``.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from rasa.config import settings
from rasa.utils import (
    DATASET_ANCHOR,
    file_sha256,
    iso_now,
    read_json,
    round_idr,
    write_json,
)

STYLES = ["minimalist", "sporty", "classic", "playful", "natural"]
STYLE_LABEL = {
    "minimalist": "minimalist",
    "sporty": "sporty",
    "classic": "classic",
    "playful": "playful",
    "natural": "natural",
}
COLORS = ["black", "white", "gray", "navy", "green", "cream", "blue", "red", "brown", "transparent"]


@dataclass(frozen=True)
class CategorySpec:
    category_id: str
    name: str
    subcategories: tuple[str, ...]
    subcategory_labels: tuple[str, ...]
    price_range: tuple[int, int]
    brands: tuple[str, ...]
    materials: tuple[str, ...]
    use_cases: tuple[str, ...]
    audiences: tuple[str, ...]
    tags: tuple[str, ...]


CATEGORY_SPECS: tuple[CategorySpec, ...] = (
    CategorySpec(
        "bag", "Bags",
        ("backpack", "tote", "sling"),
        ("Backpack", "Tote Bag", "Sling Bag"),
        (60000, 450000),
        ("Nusakita", "Sagara", "Rimba", "Cendana"),
        ("canvas", "polyester", "nylon", "synthetic leather"),
        ("daily campus use", "remote work", "short trips"),
        ("students", "young professionals", "active users"),
        ("campus", "everyday", "laptop", "lightweight"),
    ),
    CategorySpec(
        "stationery", "Stationery",
        ("pen", "pencil", "notebook", "highlighter"),
        ("Pen", "Pencil", "Notebook", "Highlighter"),
        (4000, 90000),
        ("Aksara", "Lentera", "Kanaya", "Bumi"),
        ("ABS plastic", "recycled paper", "metal", "wood"),
        ("taking class notes", "independent study", "journaling"),
        ("university students", "students", "writers"),
        ("campus", "notes", "exams", "budget-friendly"),
    ),
    CategorySpec(
        "drinkware", "Drinkware",
        ("tumbler", "bottle", "mug"),
        ("Tumbler", "Bottle", "Mug"),
        (30000, 250000),
        ("Tirta", "Sagara", "Nusakita", "Kanaya"),
        ("stainless steel", "Tritan", "glass", "ceramic"),
        ("daily campus use", "office work", "light exercise"),
        ("students", "professionals", "active users"),
        ("campus", "everyday", "leakproof", "insulated"),
    ),
    CategorySpec(
        "organizer", "Organizer",
        ("pouch", "desk_organizer", "cable_organizer"),
        ("Pouch", "Desk Organizer", "Cable Organizer"),
        (15000, 120000),
        ("Aksara", "Cendana", "Lentera"),
        ("canvas", "plastic", "wood", "silicone"),
        ("organizing a desk", "storing stationery", "managing cables"),
        ("students", "professionals", "organized users"),
        ("organized", "desk", "campus", "cables"),
    ),
    CategorySpec(
        "electronics", "Electronics",
        ("powerbank", "mouse", "keyboard", "earphone", "usb_hub"),
        ("Power Bank", "Mouse", "Keyboard", "Earphone", "USB Hub"),
        (45000, 650000),
        ("Volta", "Karsa", "Bumi", "Nusakita"),
        ("aluminum", "ABS plastic", "silicone", "metal"),
        ("remote work", "online study", "class presentations"),
        ("students", "remote professionals", "device users"),
        ("campus", "work", "usb", "wireless"),
    ),
    CategorySpec(
        "book", "Books",
        ("novel", "textbook", "journal"),
        ("Novel", "Textbook", "Journal"),
        (35000, 200000),
        ("Aksara", "Pustaka Nusa", "Lentera"),
        ("book paper", "uncoated paper", "recycled paper", "hardcover"),
        ("leisure reading", "new-semester study", "reflective writing"),
        ("students", "readers", "writers"),
        ("campus", "reading", "semester", "gift"),
    ),
    CategorySpec(
        "desk", "Desk Accessories",
        ("lamp", "stand", "mat"),
        ("Desk Lamp", "Laptop Stand", "Desk Mat"),
        (40000, 350000),
        ("Karsa", "Cendana", "Volta"),
        ("metal", "wood", "aluminum", "synthetic leather"),
        ("late-night study", "remote work", "improving posture"),
        ("students", "remote professionals", "desk users"),
        ("desk", "work", "study", "ergonomic"),
    ),
    CategorySpec(
        "personal_care", "Personal Care",
        ("sanitizer", "sunscreen", "lipbalm"),
        ("Hand Sanitizer", "Sunscreen", "Lip Balm"),
        (15000, 120000),
        ("Kanaya", "Tirta", "Rimba"),
        ("plastic bottle", "tube", "aluminum"),
        ("daily activities", "in-person classes", "travel"),
        ("students", "active users", "professionals"),
        ("everyday", "hygienic", "practical"),
    ),
    CategorySpec(
        "snack", "Snacks",
        ("biscuits", "coffee", "energy_bar"),
        ("Biscuits", "Instant Coffee", "Energy Bar"),
        (8000, 85000),
        ("Rimba", "Bumi", "Sagara"),
        ("paper packaging", "aluminum packaging", "plastic packaging"),
        ("campus snacks", "study sessions", "work breaks"),
        ("students", "professionals", "active users"),
        ("snack", "budget-friendly", "practical", "energy"),
    ),
    CategorySpec(
        "umbrella", "Umbrellas",
        ("foldable", "transparent"),
        ("Folding Umbrella", "Transparent Umbrella"),
        (30000, 150000),
        ("Sagara", "Nusakita", "Kanaya"),
        ("nylon", "polyester", "transparent plastic"),
        ("rainy campus days", "daily commuting", "outdoor activities"),
        ("students", "professionals", "active users"),
        ("rain", "folding", "everyday", "lightweight"),
    ),
)

MERCHANT_NAMES = (
    "Cendana Store", "Sejahtera Campus", "Aksara Warehouse", "Nusa Supplies",
    "Tirta Supply", "Rimba Store", "Little Lentera", "Bumi Catalog",
    "Karsa Technology", "Sagara Daily", "Kanaya Care", "Nusa Books",
    "Volta Electronics", "Aksara Station", "Cendana Living", "Kanaya Store",
    "Sagara Outdoor", "Nusakita Official", "Bumi Snack", "Tirta Drinkware",
    "Rimba Organizer", "Lentera Desk", "Karsa Workspace", "Campus Tech",
    "Sejahtera Mart", "Compact Warehouse", "Nusa Value Store", "Cendana Gift",
    "Sagara Campus", "Nusa Bag Studio",
)

CITIES = ("Bandung", "Jakarta", "Yogyakarta", "Surabaya", "Semarang", "Malang", "Denpasar", "Medan")

EVENT_TYPES = ("click", "save", "add_to_list", "purchase_proxy")
EVENT_PROBS = (0.52, 0.22, 0.16, 0.10)
EVENT_WEIGHTS = {"click": 1.0, "save": 2.0, "add_to_list": 3.0, "purchase_proxy": 4.0}


def _price_for(spec: CategorySpec, sub_idx: int, rng: np.random.Generator) -> int:
    low, high = spec.price_range
    log_low, log_high = np.log(max(low, 1000)), np.log(high)
    base = float(np.exp(rng.uniform(log_low, log_high)))
    sub_factor = 0.75 + 0.12 * sub_idx
    if rng.random() < 0.08:
        base *= 1.35
    return round_idr(max(low, min(high, base * sub_factor)))


def _review_count(age_days: int, prior: float, rng: np.random.Generator) -> int:
    age_factor = min(1.0, age_days / 180.0)
    value = rng.negative_binomial(3, 0.35) * prior * age_factor
    return int(min(900, max(0, value)))


def generate_catalog(seed: int = 42, n_products: int = 600) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(seed)

    merchants = []
    n_merchants = int(settings.dataset.n_merchants)
    for idx, name in enumerate(MERCHANT_NAMES[:n_merchants], start=1):
        low_history = idx % 5 == 0
        merchants.append(
            {
                "merchant_id": f"m{idx:03d}",
                "merchant_name": name,
                "city": CITIES[(idx - 1) % len(CITIES)],
                "rating": round(float(np.clip(rng.normal(4.45, 0.18), 3.8, 4.9)), 2),
                "is_low_history": bool(low_history),
                "exposure_factor": round(float(0.30 if low_history else rng.uniform(0.85, 1.0)), 3),
                "created_at": (DATASET_ANCHOR - timedelta(days=int(rng.integers(600, 1200)))).isoformat(),
            }
        )
    merchants_df = pd.DataFrame(merchants)

    per_category = n_products // len(CATEGORY_SPECS)
    products: list[dict] = []
    product_counter = 1
    for spec in CATEGORY_SPECS:
        for i in range(per_category):
            sub_idx = i % len(spec.subcategories)
            subcategory = spec.subcategories[sub_idx]
            sub_label = spec.subcategory_labels[sub_idx]
            brand = str(rng.choice(spec.brands))
            style = str(rng.choice(STYLES))
            color = str(rng.choice(COLORS))
            material = str(rng.choice(spec.materials))
            price = _price_for(spec, sub_idx, rng)
            rating = round(float(np.clip(rng.normal(4.32, 0.30), 3.5, 5.0)), 2)
            is_late = bool(rng.random() < settings.dataset.late_product_fraction)
            age_days = int(rng.integers(5, 28)) if is_late else int(rng.integers(90, 420))
            created_at = DATASET_ANCHOR - timedelta(days=age_days)

            # Popular merchants receive more products; low-history merchants
            # retain enough catalog share for exposure evaluation.
            weights = merchants_df["exposure_factor"].to_numpy()
            weights = weights / weights.sum()
            merchant_id = str(rng.choice(merchants_df["merchant_id"], p=weights))

            availability_roll = rng.random()
            if availability_roll < 0.075:
                availability = "unavailable"
            elif availability_roll < 0.125:
                availability = "unknown"
            else:
                availability = "available"

            prior = float(rng.lognormal(mean=0.0, sigma=0.55))
            review_count = _review_count(age_days, prior, rng)

            model_no = i + 1
            model_name = f"{sub_label} {model_no:02d}"
            product_name = f"{brand} {model_name}"
            use_case = str(rng.choice(spec.use_cases))
            audience = str(rng.choice(spec.audiences))
            style_label = STYLE_LABEL[style]

            capacity_text = ""
            if spec.category_id == "drinkware":
                capacity_ml = int(rng.choice([350, 500, 600, 750, 1000]))
                capacity_text = f" Capacity: {capacity_ml} ml."
            elif spec.category_id == "bag":
                capacity_l = int(rng.choice([14, 18, 20, 24, 28]))
                capacity_text = f" Capacity: {capacity_l} liters."
            elif spec.category_id == "book":
                pages = int(rng.choice([120, 160, 200, 240, 320]))
                capacity_text = f" {pages} pages."
            elif spec.category_id == "electronics" and subcategory == "powerbank":
                capacity_text = f" Battery capacity: {int(rng.choice([5000, 10000, 20000]))} mAh."

            description = (
                f"{product_name} is a {style_label} {sub_label.lower()} for {use_case}. "
                f"Made from {material} in {color}, it is designed for {audience}.{capacity_text} "
                f"This product is easy to carry and pair with other essentials."
            )
            attributes = {
                "color": color,
                "style": style,
                "material": material,
                "use_case": use_case,
                "audience": audience,
                "eco_friendly": bool(rng.random() < 0.35),
                "warranty_months": int(rng.choice([0, 3, 6, 12])),
                "tags": list(spec.tags),
                "synthetic": True,
            }
            if capacity_text:
                attributes["capacity_text"] = capacity_text.strip()
            # Example cross-category exclusion rule for notebooks and journals.
            if spec.category_id in {"stationery", "book"} and subcategory in {"notebook", "journal"}:
                attributes["exclusive_group"] = "paper_goods"

            products.append(
                {
                    "product_id": f"p{product_counter:04d}",
                    "product_name": product_name,
                    "category_id": spec.category_id,
                    "category_name": spec.name,
                    "subcategory": subcategory,
                    "description": description,
                    "brand": brand,
                    "price": price,
                    "rating": rating,
                    "review_count": review_count,
                    "availability_status": availability,
                    "merchant_id": merchant_id,
                    "attributes": json.dumps(attributes, ensure_ascii=False),
                    "created_at": created_at.isoformat(),
                }
            )
            product_counter += 1

    products_df = pd.DataFrame(products)

    # Ensure every category has enough available products so demo scenarios
    # do not fail because of random sampling.
    for category_id in products_df["category_id"].unique():
        mask = products_df["category_id"] == category_id
        available_idx = products_df.index[mask & (products_df["availability_status"] == "available")]
        if len(available_idx) < 15:
            need = 15 - len(available_idx)
            candidates = products_df.index[mask & (products_df["availability_status"] != "available")]
            for idx in list(candidates)[:need]:
                products_df.at[idx, "availability_status"] = "available"

    # Keep synthetic prices and ratings within realistic ranges.
    products_df["price"] = products_df["price"].clip(lower=1000).astype(int)
    products_df["rating"] = products_df["rating"].clip(3.5, 5.0)

    categories_df = pd.DataFrame(
        [
            {
                "category_id": spec.category_id,
                "category_name": spec.name,
                "description": f"Synthetic {spec.name.lower()} category for campus and everyday needs.",
                "subcategories": json.dumps(list(spec.subcategories)),
            }
            for spec in CATEGORY_SPECS
        ]
    )
    return categories_df, merchants_df, products_df


def generate_users(seed: int = 42, n_users: int = 500) -> pd.DataFrame:
    rng = np.random.default_rng(seed + 1)
    category_ids = [spec.category_id for spec in CATEGORY_SPECS]
    category_weights = np.array([2.2, 3.0, 2.6, 1.7, 1.8, 1.4, 1.3, 1.0, 1.6, 1.0])
    category_weights = category_weights / category_weights.sum()
    style_to_category = {spec.category_id: spec.brands for spec in CATEGORY_SPECS}

    users = []
    cold_count = int(round(settings.dataset.cold_user_fraction * n_users))
    for idx in range(1, n_users + 1):
        n_pref = int(rng.integers(2, 5))
        preferred_categories = list(
            rng.choice(category_ids, size=n_pref, replace=False, p=category_weights)
        )
        preferred_brands: list[str] = []
        for category_id in preferred_categories:
            preferred_brands.append(str(rng.choice(style_to_category[category_id])))
        preferred_brands = list(dict.fromkeys(preferred_brands))
        preferred_styles = list(rng.choice(STYLES, size=int(rng.integers(1, 3)), replace=False))
        preferred_colors = list(rng.choice(COLORS, size=int(rng.integers(2, 5)), replace=False))
        sensitivity = str(rng.choice(["high", "medium", "low"], p=[0.35, 0.45, 0.20]))
        is_cold = idx > n_users - cold_count
        users.append(
            {
                "user_id": f"u{idx:04d}",
                "preferred_categories": json.dumps(preferred_categories),
                "preferred_brands": json.dumps(preferred_brands),
                "preferred_styles": json.dumps(preferred_styles),
                "preferred_colors": json.dumps(preferred_colors),
                "price_sensitivity": sensitivity,
                "is_cold_start": bool(is_cold),
                "created_at": (DATASET_ANCHOR - timedelta(days=int(rng.integers(120, 900)))).isoformat(),
            }
        )
    return pd.DataFrame(users)


def _user_product_affinity(
    user: pd.Series,
    catalog: pd.DataFrame,
    merchant_exposure: dict[str, float],
    popularity: np.ndarray,
) -> np.ndarray:
    preferred_categories = set(json.loads(user["preferred_categories"]))
    preferred_brands = set(json.loads(user["preferred_brands"]))
    preferred_styles = set(json.loads(user["preferred_styles"]))
    preferred_colors = set(json.loads(user["preferred_colors"]))
    sensitivity = user["price_sensitivity"]

    cat = catalog["category_id"].isin(preferred_categories).to_numpy(dtype=float)
    brand = catalog["brand"].isin(preferred_brands).to_numpy(dtype=float)
    style = catalog["_style"].isin(preferred_styles).to_numpy(dtype=float)
    color = catalog["_color"].isin(preferred_colors).to_numpy(dtype=float)
    exposure = catalog["merchant_id"].map(merchant_exposure).to_numpy(dtype=float)

    price_rank = catalog.groupby("category_id")["price"].rank(pct=True).to_numpy()
    if sensitivity == "high":
        price_fit = 1.0 - price_rank
    elif sensitivity == "low":
        price_fit = price_rank
    else:
        price_fit = 1.0 - np.abs(price_rank - 0.45)

    # These weights control how strongly user preferences influence
    # interactions. The signal must support meaningful offline evaluation
    # while retaining noise and exploration.
    score = (
        0.44 * cat
        + 0.20 * brand
        + 0.10 * style
        + 0.05 * color
        + 0.13 * price_fit
        + 0.08 * popularity
    ) * exposure
    return np.exp(4.0 * score)


def generate_interactions(
    users: pd.DataFrame,
    catalog: pd.DataFrame,
    merchants: pd.DataFrame,
    seed: int = 42,
) -> pd.DataFrame:
    rng = np.random.default_rng(seed + 2)
    window = settings.dataset.interaction_window_days
    merchant_exposure = dict(
        zip(merchants["merchant_id"], merchants["exposure_factor"], strict=False)
    )

    catalog = catalog.copy()
    attrs = catalog["attributes"].map(json.loads)
    catalog["_style"] = attrs.map(lambda value: value.get("style", ""))
    catalog["_color"] = attrs.map(lambda value: value.get("color", ""))
    popularity_raw = catalog["review_count"].to_numpy(dtype=float) + 1.0
    popularity = popularity_raw / popularity_raw.max()

    rows: list[dict] = []
    event_counter = 1
    for _, user in users.iterrows():
        is_cold = bool(user["is_cold_start"])
        affinity = _user_product_affinity(user, catalog, merchant_exposure, popularity)
        affinity = affinity / affinity.sum()

        n_positives = int(rng.integers(1, 4)) if is_cold else int(rng.integers(18, 40))
        chosen = rng.choice(catalog.index.to_numpy(), size=n_positives, replace=False, p=affinity)
        n_sessions = 1 if is_cold else int(rng.integers(4, 9))
        session_days = np.sort(rng.integers(0, window, size=n_sessions))
        user_created = pd.Timestamp(user["created_at"]).tz_localize(None)

        for idx, product_idx in enumerate(chosen):
            session_no = idx % n_sessions
            day_offset = int(session_days[session_no])
            base_time = DATASET_ANCHOR.replace(tzinfo=None) - timedelta(
                days=day_offset, hours=int(rng.integers(1, 17)), minutes=int(rng.integers(0, 60))
            )
            if base_time < user_created:
                base_time = user_created + timedelta(days=int(rng.integers(1, 5)))

            product = catalog.loc[product_idx]
            event_type = str(rng.choice(EVENT_TYPES, p=EVENT_PROBS))
            session_id = f"sim-{user['user_id']}-{session_no:02d}"
            rows.append(
                {
                    "event_id": f"evt_{event_counter:07d}",
                    "session_id": session_id,
                    "user_id": user["user_id"],
                    "product_id": product["product_id"],
                    "event_type": event_type,
                    "event_timestamp": (base_time + timedelta(seconds=int(rng.integers(0, 900)))).isoformat(),
                    "experiment_variant": "organic",
                    "source": "synthetic_history",
                }
            )
            event_counter += 1

            # Impression in the same session, possibly before or after the interaction.
            n_impressions = int(rng.integers(2, 5))
            impression_pool = rng.choice(
                catalog.index.to_numpy(), size=n_impressions, replace=False,
                p=popularity / popularity.sum(),
            )
            for impression_idx in impression_pool:
                impression_product = catalog.loc[impression_idx]
                same = impression_product["product_id"] == product["product_id"]
                impression_time = base_time - timedelta(seconds=int(rng.integers(5, 600)))
                rows.append(
                    {
                        "event_id": f"evt_{event_counter:07d}",
                        "session_id": session_id,
                        "user_id": user["user_id"],
                        "product_id": impression_product["product_id"],
                        "event_type": "impression" if not same else "click",
                        "event_timestamp": impression_time.isoformat(),
                        "experiment_variant": "organic",
                        "source": "synthetic_history",
                    }
                )
                event_counter += 1

    interactions = pd.DataFrame(rows)
    interactions = interactions.drop_duplicates(subset=["event_id"])
    interactions["event_timestamp"] = pd.to_datetime(interactions["event_timestamp"])
    interactions = interactions.sort_values(["event_timestamp", "event_id"]).reset_index(drop=True)
    return interactions


def generate_dataset(seed: int | None = None, n_products: int | None = None) -> dict:
    seed = settings.seed if seed is None else seed
    n_products = settings.dataset.n_products if n_products is None else n_products
    out_dir = settings.raw_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    categories, merchants, products = generate_catalog(seed=seed, n_products=n_products)
    users = generate_users(seed=seed)
    interactions = generate_interactions(users, products, merchants, seed=seed)

    categories.to_csv(out_dir / "categories.csv", index=False, encoding="utf-8")
    merchants.to_csv(out_dir / "merchants.csv", index=False, encoding="utf-8")
    products.to_csv(out_dir / "products.csv", index=False, encoding="utf-8")
    users.to_csv(out_dir / "users.csv", index=False, encoding="utf-8")
    interactions.to_csv(out_dir / "interactions.csv", index=False, encoding="utf-8")

    manifest = {
        "dataset_name": settings.dataset.name,
        "dataset_version": settings.dataset.version,
        "generated_at": iso_now(),
        "seed": seed,
        "synthetic": True,
        "n_categories": int(len(categories)),
        "n_merchants": int(len(merchants)),
        "n_products": int(len(products)),
        "n_users": int(len(users)),
        "n_events": int(len(interactions)),
        "n_positive_events": int((interactions["event_type"] != "impression").sum()),
        "interaction_window_days": settings.dataset.interaction_window_days,
        "anchor_date": settings.dataset.anchor_date,
        "files": {
            name: {
                "rows": int(len(frame)),
                "sha256": file_sha256(out_dir / name),
            }
            for name, frame in {
                "categories.csv": categories,
                "merchants.csv": merchants,
                "products.csv": products,
                "users.csv": users,
                "interactions.csv": interactions,
            }.items()
        },
        "license": "CC-BY-4.0 (synthetic data, not real marketplace data)",
        "warning": (
            "All products, merchants, prices, inventory, and interactions are simulated. "
            "They do not represent a real marketplace or real users."
        ),
    }
    write_json(out_dir / "dataset_manifest.json", manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the synthetic RASA dataset")
    parser.add_argument("--seed", type=int, default=settings.seed)
    parser.add_argument("--products", type=int, default=settings.dataset.n_products)
    args = parser.parse_args()
    manifest = generate_dataset(seed=args.seed, n_products=args.products)
    print(json.dumps(manifest, indent=2, ensure_ascii=False)[:1200])


if __name__ == "__main__":
    main()
