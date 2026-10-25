"""Ekstraksi misi dari bahasa alami (rule-based, tanpa LLM berbayar).

PRD FR-020 (Could): hasil ekstraksi WAJIB ditinjau pengguna sebelum dipakai.
Parser ini deterministik dan hanya mengekstrak struktur; tidak mengarang harga,
stok, atau rating.
"""

from __future__ import annotations

import re
from typing import Any

from rasa.missions.validation import Preferences

CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "bag": ("tas ransel", "ransel", "backpack", "tas tote", "tote bag", "tas selempang", "tas"),
    "stationery": (
        "alat tulis", "buku catatan", "buku tulis", "pulpen", "pensil", "stabilo",
        "highlighter", "notebook", "penghapus",
    ),
    "drinkware": ("botol minum", "botol", "tumbler", "mug", "gelas", "drinkware"),
    "organizer": ("organizer meja", "pengatur kabel", "organizer", "pouch", "tempat pensil"),
    "electronics": (
        "power bank", "powerbank", "mouse", "keyboard", "earphone", "headset",
        "usb hub", "elektronik",
    ),
    "book": ("buku pelajaran", "buku", "novel", "jurnal"),
    "desk": ("lampu meja", "stand laptop", "mat meja", "perlengkapan meja", "meja kerja"),
    "personal_care": ("hand sanitizer", "sanitizer", "tabir surya", "sunscreen", "lip balm", "perawatan diri"),
    "snack": ("energy bar", "kopi", "biskuit", "camilan", "snack", "makanan ringan"),
    "umbrella": ("payung lipat", "payung transparan", "payung"),
}

STYLE_KEYWORDS = {
    "minimalist": ("minimalis", "minimalist", "sederhana"),
    "sporty": ("sporty", "olahraga"),
    "klasik": ("klasik", "classic"),
    "playful": ("ceria", "playful", "warna-warni"),
    "natural": ("natural", "alami", "earth tone", "netral", "neutral"),
}

COLOR_KEYWORDS = {
    "hitam": ("hitam", "black"),
    "putih": ("putih", "white"),
    "abu": ("abu", "grey", "gray"),
    "navy": ("navy", "biru tua"),
    "hijau": ("hijau", "green"),
    "krem": ("krem", "cream", "beige"),
    "biru": ("biru", "blue"),
    "merah": ("merah", "red"),
    "cokelat": ("cokelat", "brown"),
    "transparan": ("transparan", "clear"),
}

NUMBER_WORDS = {
    "satu": 1, "dua": 2, "tiga": 3, "empat": 4, "lima": 5,
    "enam": 6, "tujuh": 7, "delapan": 8, "sembilan": 9, "sepuluh": 10,
}

MONEY_PATTERN = re.compile(
    r"(?:rp\.?\s*)?(\d{1,3}(?:\.\d{3})+|\d+(?:,\d+)?)\s*(juta|jt|ribu|rb|k)?",
    re.IGNORECASE,
)
MERCHANT_PATTERN = re.compile(
    r"(?:maks(?:imal|\.)?|paling banyak|maksimal|hingga|dari)?\s*"
    r"(\d+|satu|dua|tiga|empat|lima|enam|tujuh|delapan|sembilan|sepuluh)\s*"
    r"(?:toko|merchant|penjual)",
    re.IGNORECASE,
)
RATING_PATTERN = re.compile(
    r"rating(?:\s*(?:minimal|min\.?))?\s*(?:di atas|minimal|>=|:)?\s*(\d(?:[.,]\d)?)",
    re.IGNORECASE,
)
BUDGET_CONTEXT = re.compile(
    r"(anggaran|budget|maksimal|maks\.?|maks|di bawah|kurang dari|s.d\.?|sampai|rp)",
    re.IGNORECASE,
)


def _parse_money(raw_number: str, unit: str | None) -> float | None:
    text = raw_number.strip()
    multiplier = 1.0
    if unit:
        unit_lower = unit.lower()
        if unit_lower in {"juta", "jt"}:
            multiplier = 1_000_000
        elif unit_lower in {"ribu", "rb", "k"}:
            multiplier = 1_000
    if "." in text and re.fullmatch(r"\d{1,3}(?:\.\d{3})+", text):
        value = float(text.replace(".", ""))
    else:
        value = float(text.replace(",", "."))
    return value * multiplier


def extract_budget(text: str) -> tuple[float | None, str | None]:
    candidates: list[tuple[float, int, str]] = []
    for match in MONEY_PATTERN.finditer(text):
        number, unit = match.group(1), match.group(2)
        # Abaikan angka yang jelas bukan uang (mis. "2 toko").
        tail = text[match.end(): match.end() + 12].lower()
        if re.match(r"\s*(toko|merchant|orang|hari|minggu|bulan|tahun|kategori)", tail):
            continue
        value = _parse_money(number, unit)
        if value is None or value < 100:
            continue
        window = text[max(0, match.start() - 35): match.start()].lower()
        has_context = bool(BUDGET_CONTEXT.search(window)) or bool(unit) or "rp" in match.group(0).lower()
        if not has_context:
            continue
        candidates.append((value, match.start(), match.group(0).strip()))
    if not candidates:
        return None, None
    value, _, snippet = candidates[0]
    return value, snippet


def detect_categories(text: str) -> tuple[list[str], list[str], list[str]]:
    required: list[str] = []
    optional: list[str] = []
    matched_terms: list[str] = []
    remaining = text.lower()

    # Frasa terpanjang diproses lebih dulu agar "buku catatan" tidak menjadi "buku".
    keyword_pairs = [
        (keyword, category_id)
        for category_id, keywords in CATEGORY_KEYWORDS.items()
        for keyword in keywords
    ]
    keyword_pairs.sort(key=lambda item: len(item[0]), reverse=True)

    for keyword, category_id in keyword_pairs:
        if category_id in required or category_id in optional:
            continue
        pattern = re.compile(rf"\b{re.escape(keyword)}\b", re.IGNORECASE)
        match = pattern.search(remaining)
        if not match:
            continue
        context = remaining[max(0, match.start() - 30): match.end() + 30]
        if "opsional" in context or "kalau ada" in context or "jika memungkinkan" in context:
            optional.append(category_id)
        else:
            required.append(category_id)
        matched_terms.append(keyword)
        remaining = remaining[: match.start()] + " " * (match.end() - match.start()) + remaining[match.end():]

    return required, optional, matched_terms


def extract_merchants(text: str) -> int | None:
    match = MERCHANT_PATTERN.search(text)
    if not match:
        return None
    raw = match.group(1).lower()
    value = NUMBER_WORDS.get(raw)
    if value is None:
        try:
            value = int(raw)
        except ValueError:
            return None
    return value if value >= 1 else None


def extract_rating(text: str) -> float | None:
    match = RATING_PATTERN.search(text)
    if not match:
        return None
    value = float(match.group(1).replace(",", "."))
    return value if 0 <= value <= 5 else None


def parse_mission_text(text: str) -> dict[str, Any]:
    clean = " ".join((text or "").strip().split())
    lowered = clean.lower()
    budget, budget_snippet = extract_budget(lowered)
    max_merchants = extract_merchants(lowered)
    minimum_rating = extract_rating(lowered)
    required, optional, matched_terms = detect_categories(lowered)

    styles = [
        style for style, keywords in STYLE_KEYWORDS.items()
        if any(re.search(rf"\b{re.escape(word)}\b", lowered) for word in keywords)
    ]
    colors = [
        color for color, keywords in COLOR_KEYWORDS.items()
        if any(re.search(rf"\b{re.escape(word)}\b", lowered) for word in keywords)
    ]

    notes: list[str] = [
        "Ekstraksi ini menggunakan aturan kata kunci dan harus dikonfirmasi sebelum dipakai.",
    ]
    if budget is None:
        notes.append("Anggaran tidak terdeteksi; pengguna perlu mengisinya manual.")
    if not required and not optional:
        notes.append("Kategori tidak terdeteksi; pilih kategori secara manual.")
    if max_merchants is None:
        notes.append("Batas jumlah toko tidak terdeteksi; nilai default 2 dipakai setelah konfirmasi.")
    if minimum_rating is not None and not (3.5 <= minimum_rating <= 5.0):
        notes.append("Rating minimum di luar skala dataset 3,5-5,0; periksa kembali.")
        minimum_rating = None

    # Kategori opsional dibatasi agar scope misi tetap jelas.
    if len(required) > 6:
        optional.extend(required[6:])
        required = required[:6]

    fields_found = sum(
        [budget is not None, bool(required), max_merchants is not None,
         minimum_rating is not None, bool(styles), bool(colors)]
    )
    confidence = round(min(0.95, 0.40 + 0.09 * fields_found), 2)

    goal = clean
    for prefix in ("saya ingin ", "aku ingin ", "tolong ", "bantu saya "):
        if goal.lower().startswith(prefix):
            goal = goal[len(prefix):]
            break

    mission = {
        "goal": goal[:500],
        "required_categories": required,
        "optional_categories": optional,
        "max_budget": budget,
        "max_merchants": max_merchants if max_merchants is not None else 2,
    }
    preferences = Preferences(
        style=styles,
        colors=colors,
        brands=[],
        minimum_rating=minimum_rating,
        max_item_price=None,
    )
    return {
        "source_text": clean,
        "mission": mission,
        "preferences": preferences.to_dict(),
        "confidence": confidence,
        "matched_terms": matched_terms,
        "budget_snippet": budget_snippet,
        "notes": notes,
        "requires_confirmation": True,
    }
