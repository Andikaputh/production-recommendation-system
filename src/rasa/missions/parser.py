"""Rule-based natural-language mission extraction.

PRD FR-020 requires users to review extracted fields before applying them. The
parser is deterministic, extracts structure only, and never invents prices,
inventory, or ratings.
"""

from __future__ import annotations

import re
from typing import Any

from rasa.missions.validation import Preferences

CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "bag": ("backpack", "tote bag", "sling bag", "bag"),
    "stationery": (
        "stationery", "notebook", "pen", "pencil", "highlighter", "eraser",
    ),
    "drinkware": ("water bottle", "bottle", "tumbler", "mug", "cup", "drinkware"),
    "organizer": ("desk organizer", "cable organizer", "organizer", "pouch", "pencil case"),
    "electronics": (
        "power bank", "powerbank", "mouse", "keyboard", "earphone", "headset",
        "usb hub", "electronics",
    ),
    "book": ("textbook", "book", "novel", "journal"),
    "desk": ("desk lamp", "laptop stand", "desk mat", "desk accessories", "workspace"),
    "personal_care": ("hand sanitizer", "sanitizer", "sunscreen", "lip balm", "personal care"),
    "snack": ("energy bar", "coffee", "biscuits", "snack", "light meal"),
    "umbrella": ("folding umbrella", "transparent umbrella", "umbrella"),
}

STYLE_KEYWORDS = {
    "minimalist": ("minimalist", "simple"),
    "sporty": ("sporty", "athletic"),
    "classic": ("classic", "timeless"),
    "playful": ("playful", "colorful"),
    "natural": ("natural", "earth tone", "neutral"),
}

COLOR_KEYWORDS = {
    "black": ("black",),
    "white": ("white",),
    "gray": ("gray", "grey"),
    "navy": ("navy", "dark blue"),
    "green": ("green",),
    "cream": ("cream", "beige"),
    "blue": ("blue",),
    "red": ("red",),
    "brown": ("brown",),
    "transparent": ("transparent", "clear"),
}

NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}

MONEY_PATTERN = re.compile(
    r"(?:idr|rp\.?|\$)?\s*(\d{1,3}(?:[.,]\d{3})+|\d+(?:[.,]\d+)?)\s*(million|m|thousand|k)?",
    re.IGNORECASE,
)
MERCHANT_PATTERN = re.compile(
    r"(?:maximum|max\.?|up to|from)?\s*"
    r"(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s*"
    r"(?:stores?|merchants?|sellers?)",
    re.IGNORECASE,
)
RATING_PATTERN = re.compile(
    r"rating(?:\s*(?:minimum|min\.?))?\s*(?:above|minimum|>=|:)?\s*(\d(?:[.,]\d)?)",
    re.IGNORECASE,
)
BUDGET_CONTEXT = re.compile(
    r"(budget|maximum|max\.?|under|less than|up to|idr|rp|\$)",
    re.IGNORECASE,
)


def _parse_money(raw_number: str, unit: str | None) -> float | None:
    text = raw_number.strip()
    multiplier = 1.0
    if unit:
        unit_lower = unit.lower()
        if unit_lower in {"million", "m"}:
            multiplier = 1_000_000
        elif unit_lower in {"thousand", "k"}:
            multiplier = 1_000
    if re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", text):
        value = float(text.replace(".", "").replace(",", ""))
    else:
        value = float(text.replace(",", "."))
    return value * multiplier


def extract_budget(text: str) -> tuple[float | None, str | None]:
    candidates: list[tuple[float, int, str]] = []
    for match in MONEY_PATTERN.finditer(text):
        number, unit = match.group(1), match.group(2)
        # Ignore numbers that clearly are not monetary values, such as "2 merchants".
        tail = text[match.end(): match.end() + 12].lower()
        if re.match(r"\s*(stores?|merchants?|people|days?|weeks?|months?|years?|categories)", tail):
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

    # Process longer phrases first so "water bottle" does not degrade to "bottle".
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
        if "optional" in context or "if available" in context or "if possible" in context:
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
        "This extraction uses keyword rules and must be confirmed before use.",
    ]
    if budget is None:
        notes.append("No budget was detected; enter it manually.")
    if not required and not optional:
        notes.append("No category was detected; select categories manually.")
    if max_merchants is None:
        notes.append("No merchant limit was detected; the default value of 2 is used after confirmation.")
    if minimum_rating is not None and not (3.5 <= minimum_rating <= 5.0):
        notes.append("The minimum rating is outside the dataset range of 3.5 to 5.0; review it.")
        minimum_rating = None

    # Limit optional categories so the mission remains focused.
    if len(required) > 6:
        optional.extend(required[6:])
        required = required[:6]

    fields_found = sum(
        [budget is not None, bool(required), max_merchants is not None,
         minimum_rating is not None, bool(styles), bool(colors)]
    )
    confidence = round(min(0.95, 0.40 + 0.09 * fields_found), 2)

    goal = clean
    for prefix in ("i want ", "i need ", "please ", "help me "):
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
