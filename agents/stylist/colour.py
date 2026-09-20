"""Deterministic colour theory for the stylist (DECISIONS §5.9). No LLM touches a pairing score:
Gemini (or the stub) only decides how to talk about a look; this module decides which hue families
go together and by how much.

Wheel: the 12-hue RYB artist's wheel (the fashion-classic one -- complements are mustard/indigo,
red/green, blue/orange -- not RGB's red/cyan) plus a fixed set of neutrals that pair with anything.
"""
from __future__ import annotations

from dataclasses import dataclass

HUES: list[str] = [
    "red", "red-orange", "orange", "yellow-orange", "yellow", "yellow-green",
    "green", "blue-green", "blue", "blue-violet", "violet", "red-violet",
]
NEUTRALS: list[str] = ["white", "black", "grey", "beige", "denim", "navy"]
ALL_FAMILIES: list[str] = HUES + NEUTRALS

# Multi-word aliases are matched first (longest phrase wins), then single words. Every value here
# must be a member of ALL_FAMILIES; asserted by tests/unit/test_colour.py.
MULTI_WORD_ALIASES: dict[str, str] = {
    "mustard yellow": "yellow-orange", "navy blue": "navy", "bottle green": "green",
    "sky blue": "blue", "off white": "white", "rani pink": "red-violet",
    "royal blue": "blue", "hot pink": "red-violet", "baby pink": "red-violet",
    "dusty pink": "red-violet", "forest green": "green", "wine red": "red",
}
SINGLE_WORD_ALIASES: dict[str, str] = {
    "red": "red", "crimson": "red", "maroon": "red", "wine": "red", "burgundy": "red",
    "rust": "red-orange", "coral": "red-orange", "peach": "red-orange", "terracotta": "red-orange",
    "orange": "orange", "tangerine": "orange",
    "mustard": "yellow-orange", "amber": "yellow-orange", "saffron": "yellow-orange",
    "yellow": "yellow", "gold": "yellow", "golden": "yellow", "lemon": "yellow",
    "olive": "yellow-green", "lime": "yellow-green", "chartreuse": "yellow-green",
    "green": "green", "emerald": "green", "mint": "green", "sage": "green", "jade": "green",
    "teal": "blue-green", "turquoise": "blue-green", "seagreen": "blue-green",
    "blue": "blue", "cobalt": "blue", "cerulean": "blue", "royal": "blue",
    "indigo": "blue-violet", "periwinkle": "blue-violet",
    "purple": "violet", "violet": "violet", "lavender": "violet", "plum": "violet", "lilac": "violet",
    "magenta": "red-violet", "pink": "red-violet", "fuchsia": "red-violet", "blush": "red-violet",
    "rani": "red-violet",
    "white": "white", "cream": "white", "ivory": "white", "off-white": "white",
    "black": "black", "charcoal": "grey", "silver": "grey", "grey": "grey", "gray": "grey",
    "beige": "beige", "tan": "beige", "khaki": "beige", "camel": "beige", "sand": "beige", "nude": "beige",
    "denim": "denim", "chambray": "denim",
    "navy": "navy",
}
KN_COLOURS: dict[str, str] = {
    "ಕೆಂಪು": "red", "ನೀಲಿ": "blue", "ಹಳದಿ": "yellow", "ಹಸಿರು": "green",
    "ಬಿಳಿ": "white", "ಕಪ್ಪು": "black", "ಗುಲಾಬಿ": "red-violet", "ಕಿತ್ತಳೆ": "orange",
}

_METAL_FAMILIES: dict[str, str] = {"gold": "yellow", "silver": "grey", "rose gold": "red-orange", "oxidised": "grey"}

REASONS = ("complementary", "analogous", "split-complementary", "triadic", "neutral anchor", "tonal")


def family_of(word: str | None) -> str | None:
    """Resolve a free-text colour word/phrase to a wheel family, or None if unknown."""
    if not word:
        return None
    low = word.strip().lower()
    if low in ALL_FAMILIES:
        return low
    if low in _METAL_FAMILIES:
        return _METAL_FAMILIES[low]
    for phrase, fam in MULTI_WORD_ALIASES.items():
        if phrase in low:
            return fam
    for token in low.replace("-", " ").split():
        if token in SINGLE_WORD_ALIASES:
            return SINGLE_WORD_ALIASES[token]
    for kn, fam in KN_COLOURS.items():
        if kn in word:
            return fam
    return None


def is_neutral(family: str | None) -> bool:
    return family in NEUTRALS


def _hue_index(family: str) -> int | None:
    return HUES.index(family) if family in HUES else None


def complementary(family: str | None) -> str | None:
    i = _hue_index(family)
    return HUES[(i + 6) % 12] if i is not None else None


def analogous(family: str | None) -> list[str]:
    i = _hue_index(family)
    if i is None:
        return []
    return [HUES[(i - 1) % 12], HUES[(i + 1) % 12]]


def analogous_wide(family: str | None) -> list[str]:
    """Two steps out on the wheel: a looser analogous pairing than `analogous`."""
    i = _hue_index(family)
    if i is None:
        return []
    return [HUES[(i - 2) % 12], HUES[(i + 2) % 12]]


def split_complementary(family: str | None) -> list[str]:
    i = _hue_index(family)
    if i is None:
        return []
    return [HUES[(i + 5) % 12], HUES[(i - 5) % 12]]


def triadic(family: str | None) -> list[str]:
    i = _hue_index(family)
    if i is None:
        return []
    return [HUES[(i + 4) % 12], HUES[(i - 4) % 12]]


def tonal(family: str | None) -> list[str]:
    return [family] if family else []


_OCCASION_WEIGHTS: dict[str, dict[str, float]] = {
    "office": {"neutral anchor": 0.10, "tonal": 0.05, "complementary": -0.15, "triadic": -0.15, "split-complementary": -0.10},
    "festive": {"complementary": 0.10, "triadic": 0.05, "tonal": -0.05},
    "wedding": {"complementary": 0.10, "triadic": 0.05, "tonal": -0.05},
    "party": {"complementary": 0.05},
}


def pairing_rules(colour: str | None, garment_type: str | None = None, occasion: str | None = None) -> dict:
    """Every family that goes with `colour`, ranked by a fixed colour-theory score and adjusted for
    occasion. `garment_type` is accepted for future per-garment tuning but does not change the
    score today. Returns {colour, family, known, pairs: [{family, score, reason}], avoid}."""
    family = family_of(colour)
    weights = _OCCASION_WEIGHTS.get(occasion or "", {})
    pairs: dict[str, tuple[float, str]] = {}

    def _offer(fam: str, score: float, reason: str) -> None:
        adjusted = round(min(1.0, max(0.0, score + weights.get(reason, 0.0))), 3)
        cur = pairs.get(fam)
        if cur is None or adjusted > cur[0]:
            pairs[fam] = (adjusted, reason)

    if family is None:
        # Unknown colour: only neutrals are safe to suggest, at a modest confidence.
        for n in NEUTRALS:
            _offer(n, 0.60, "neutral anchor")
    elif is_neutral(family):
        for h in HUES:
            _offer(h, 0.75, "neutral anchor")
        for n in NEUTRALS:
            _offer(n, 0.85 if {family, n} == {"black", "white"} else 0.70, "tonal")
    else:
        comp = complementary(family)
        if comp:
            _offer(comp, 0.90, "complementary")
        for fam in analogous(family):
            _offer(fam, 0.80, "analogous")
        for fam in analogous_wide(family):
            _offer(fam, 0.55, "analogous")
        for fam in split_complementary(family):
            _offer(fam, 0.75, "split-complementary")
        for fam in triadic(family):
            _offer(fam, 0.70, "triadic")
        _offer(family, 0.60, "tonal")
        for n in NEUTRALS:
            _offer(n, 0.75, "neutral anchor")

    ranked = sorted(({"family": f, "score": s, "reason": r} for f, (s, r) in pairs.items()), key=lambda p: (-p["score"], p["family"]))
    avoid = [] if family is None else [f for f in HUES if f not in pairs and f != family]
    return {"colour": colour, "family": family, "known": family is not None, "pairs": ranked, "avoid": avoid}


@dataclass(frozen=True)
class SkinToneRules:
    favour: tuple[str, ...]
    soften: tuple[str, ...]
    metal: str


_WARM_FAVOUR = ("yellow-orange", "orange", "red-orange", "yellow", "yellow-green", "beige")
_COOL_FAVOUR = ("blue", "blue-violet", "violet", "red-violet", "blue-green", "grey", "white", "navy")


def skin_tone_rules(undertone: str, depth: str) -> SkinToneRules:
    """Seasonal-colour-analysis heuristics, coarse by design: which hue families are generally
    flattering for a warm/cool/neutral undertone, which to soften, and which metal (gold/silver)
    suits it. `depth` (light/medium/deep) is read by `skin_adjustment` to bias saturation, not
    family membership, so it is not branched on here."""
    if undertone == "warm":
        return SkinToneRules(favour=_WARM_FAVOUR, soften=_COOL_FAVOUR, metal="gold")
    if undertone == "cool":
        return SkinToneRules(favour=_COOL_FAVOUR, soften=_WARM_FAVOUR, metal="silver")
    # neutral: both lists favoured, neither softened
    return SkinToneRules(favour=_WARM_FAVOUR + _COOL_FAVOUR, soften=(), metal="gold")


_FACE_ADJACENT_ROLES = {"top", "dress", "layer"}
_FACE_ADJACENT_ACCESSORIES = {"scarf", "earrings", "necklace"}


def skin_adjustment(family: str | None, role: str, rules: SkinToneRules, metal: str | None = None, garment_type: str | None = None, depth: str = "medium") -> tuple[float, str | None]:
    """An additive nudge to a pairing score from the customer's skin-tone profile: never enough to
    remove a candidate (capped at +/-0.10), and only applied to items worn near the face -- tops,
    dresses, layers, and face-adjacent accessories (scarves, earrings, necklaces); never footwear,
    belts or bags."""
    if role not in _FACE_ADJACENT_ROLES and garment_type not in _FACE_ADJACENT_ACCESSORIES:
        return 0.0, None
    if metal:
        if metal == rules.metal:
            return 0.10, f"suits {rules.metal}-toned skin"
        return -0.05, None
    if family is None:
        return 0.0, None
    undertone = "warm" if rules.metal == "gold" else "cool"
    if family in rules.favour:
        return 0.10, f"suits {undertone} undertone"
    if family in rules.soften:
        return -0.10, f"softer on {undertone} undertone"
    return 0.0, None
