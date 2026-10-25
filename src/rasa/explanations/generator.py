"""Tahap E - Explanation generator.

Alasan HARUS berasal dari fitur/aturan yang benar-benar dipakai ranking dan
basket optimizer. Tidak ada narasi yang mengarang stok, harga, rating, atau
atribut produk.
"""

from __future__ import annotations

from typing import Any

from rasa.missions.validation import Mission, Preferences
from rasa.utils import format_idr


def _reason(code: str, label: str, detail: str, strength: float = 0.5) -> dict[str, Any]:
    return {
        "code": code,
        "label": label,
        "detail": detail,
        "strength": round(float(max(0.0, min(1.0, strength))), 3),
    }


def build_item_reasons(
    row: dict[str, Any],
    components: dict[str, float],
    mission: Mission,
    preferences: Preferences,
    flags: dict[str, Any],
    allocation: dict[str, float] | None = None,
) -> list[dict[str, Any]]:
    reasons: list[dict[str, Any]] = []
    category_id = row.get("category_id", "")
    category_name = row.get("category_name", category_id)
    price = float(row.get("price", 0))
    rating = float(row.get("rating", 0))
    target_budget = (allocation or {}).get(category_id, mission.max_budget)

    if category_id in mission.required_categories:
        reasons.append(_reason(
            "required_category",
            f"Kategori wajib {category_name}",
            f"Produk ini memenuhi kategori wajib {category_name} pada misi Anda.",
            1.0,
        ))
    elif category_id in mission.optional_categories:
        reasons.append(_reason(
            "optional_category",
            f"Kategori opsional {category_name}",
            f"Produk ini termasuk kategori opsional {category_name}.",
            0.6,
        ))

    if components.get("content", 0.0) >= 0.45:
        reasons.append(_reason(
            "content_match",
            "Deskripsi relevan dengan tujuan",
            f"Kemiripan konten {components['content']:.2f} terhadap tujuan misi dan atribut yang Anda pilih.",
            components["content"],
        ))

    matched_attributes: list[str] = []
    if preferences.style and row.get("style") in preferences.style:
        matched_attributes.append(f"gaya {row.get('style')}")
    if preferences.colors and row.get("color") in preferences.colors:
        matched_attributes.append(f"warna {row.get('color')}")
    if preferences.brands and row.get("brand") in preferences.brands:
        matched_attributes.append(f"merek {row.get('brand')}")
    if matched_attributes:
        reasons.append(_reason(
            "preference_match",
            "Sesuai preferensi",
            "Cocok dengan preferensi Anda: " + ", ".join(matched_attributes) + ".",
            0.8,
        ))

    if preferences.minimum_rating is not None:
        reasons.append(_reason(
            "rating_threshold",
            "Memenuhi batas rating",
            f"Rating {rating:.1f} memenuhi batas minimum {preferences.minimum_rating:.1f}.",
            0.7,
        ))
    elif rating >= 4.5:
        reasons.append(_reason(
            "high_rating",
            "Rating tinggi",
            f"Rating {rating:.1f} termasuk tinggi pada katalog simulasi.",
            0.6,
        ))

    if price <= target_budget:
        reasons.append(_reason(
            "price_fit",
            "Harga sesuai alokasi",
            f"{format_idr(price)} masih di bawah alokasi kategori {format_idr(target_budget)}.",
            0.65,
        ))
    else:
        reasons.append(_reason(
            "price_tradeoff",
            "Trade-off harga",
            f"{format_idr(price)} melebihi alokasi lunak kategori {format_idr(target_budget)}, "
            "namun tetap dalam anggaran total.",
            0.4,
        ))

    if (
        (flags.get("user_known") or flags.get("session_personalized"))
        and components.get("affinity", 0.0) >= 0.35
    ):
        reasons.append(_reason(
            "history_affinity",
            "Sesuai kebiasaan belanja",
            "Merek, subkategori, gaya, atau warna produk ini mirip dengan produk yang "
            "pernah Anda beri respons.",
            components["affinity"],
        ))

    if flags.get("user_known") and components.get("collaborative", 0.0) >= 0.35:
        reasons.append(_reason(
            "personalization",
            "Sesuai histori interaksi",
            "Skor kolaboratif menunjukkan kemiripan dengan produk yang pernah Anda beri respons.",
            components["collaborative"],
        ))
    if flags.get("session_personalized") and components.get("collaborative", 0.0) >= 0.25:
        reasons.append(_reason(
            "session_personalization",
            "Menyesuaikan feedback sesi",
            "Rekomendasi mempertimbangkan produk yang baru Anda beri feedback pada sesi ini.",
            components["collaborative"],
        ))

    if flags.get("low_history_item"):
        reasons.append(_reason(
            "controlled_exposure",
            "Eksplorasi terkontrol",
            "Produk berhistori rendah tetapi melewati ambang kualitas dan relevansi; "
            "ditampilkan secara terbatas.",
            0.35,
        ))
    if flags.get("cold_start_item"):
        reasons.append(_reason(
            "cold_start_item",
            "Produk baru",
            "Produk belum memiliki histori interaksi; penilaian memakai metadata, konten, dan kualitas.",
            0.3,
        ))

    reasons.sort(key=lambda item: item["strength"], reverse=True)
    return reasons[:5]


def build_basket_explanations(
    basket: dict[str, Any],
    mission: Mission,
    diagnostics: dict[str, Any],
) -> list[dict[str, Any]]:
    explanations: list[dict[str, Any]] = []
    items = basket.get("items", [])
    if not items:
        return explanations

    if basket.get("feasible"):
        explanations.append(_reason(
            "budget_ok",
            "Anggaran terpenuhi",
            f"Total {format_idr(basket['total_price'])} dari anggaran "
            f"{format_idr(mission.max_budget)}; sisa {format_idr(basket['budget_remaining'])}.",
            1.0,
        ))
        coverage = float(basket.get("required_category_coverage", 0.0))
        explanations.append(_reason(
            "coverage",
            "Kategori wajib terpenuhi",
            f"{coverage * 100:.0f}% kategori wajib berhasil diisi.",
            coverage,
        ))
        explanations.append(_reason(
            "merchants",
            "Jumlah toko terkendali",
            f"Keranjang menggunakan {basket['merchant_count']} toko "
            f"(batas {mission.max_merchants}).",
            0.8 if basket["merchant_count"] <= mission.max_merchants else 0.2,
        ))
        if diagnostics.get("objective_value") is not None:
            explanations.append(_reason(
                "optimizer",
                "Kombinasi dioptimalkan",
                "Nilai misi kombinasi ini adalah yang tertinggi di antara kandidat yang "
                "memenuhi seluruh batasan keras.",
                0.9,
            ))
        if diagnostics.get("solver") == "greedy_fallback":
            explanations.append(_reason(
                "solver_fallback",
                "Mode heuristik",
                "Optimizer ILP tidak selesai dalam batas waktu; keranjang disusun dengan "
                "heuristik greedy yang tetap memeriksa seluruh batasan keras.",
                0.5,
            ))
    else:
        explanations.append(_reason(
            "infeasible",
            "Tidak ada kombinasi yang memenuhi seluruh batasan",
            "Sistem tidak menghapus batasan keras secara diam-diam. Lihat saran pelonggaran.",
            1.0,
        ))
    return explanations


def build_tradeoffs(
    basket: dict[str, Any],
    alternative: dict[str, Any] | None,
) -> list[str]:
    if not alternative:
        return []
    tradeoffs: list[str] = []
    basket_total = float(basket.get("total_price", 0))
    alt_total = float(alternative.get("total_price", 0))
    if alt_total > basket_total:
        tradeoffs.append(
            f"Alternatif lebih mahal {format_idr(alt_total - basket_total)} tetapi memiliki "
            "skor relevansi agregat yang berbeda."
        )
    elif alt_total < basket_total:
        tradeoffs.append(
            f"Alternatif lebih murah {format_idr(basket_total - alt_total)} dengan kemungkinan "
            "kualitas atau kecocokan preferensi yang lebih rendah."
        )
    if alternative.get("merchant_count", 0) != basket.get("merchant_count", 0):
        tradeoffs.append(
            f"Jumlah toko berbeda: {basket.get('merchant_count')} vs "
            f"{alternative.get('merchant_count')}."
        )
    if alternative.get("required_category_coverage", 1.0) < basket.get("required_category_coverage", 1.0):
        tradeoffs.append("Alternatif tidak memenuhi seluruh kategori wajib.")
    return tradeoffs
