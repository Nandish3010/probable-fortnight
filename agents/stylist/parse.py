"""Deterministic free-text garment parser (DECISIONS §5.9). No LLM involved: extracting garment
type, colour and occasion from a sentence like "a mustard yellow kurta" or "navy blue T-shirt" is a
vocabulary lookup over the same GARMENTS/COLOUR_WORDS/OCCASIONS tables the generator used to build
the catalogue, so the words the stylist understands are exactly the words the catalogue uses.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from data.generator.apparel import FABRICS, GARMENTS, OCCASIONS, PATTERNS

from .colour import KN_COLOURS, MULTI_WORD_ALIASES, SINGLE_WORD_ALIASES, family_of

_GARMENT_SYNONYMS: dict[str, str] = {"tee": "t-shirt", "tshirt": "t-shirt", "t shirt": "t-shirt", "kurti": "kurta", "pants": "trousers", "pant": "trousers", "denims": "jeans", "denim jeans": "jeans", "shoes": "sneakers", "heel": "heels", "sandal": "sandals", "bag": "handbag"}
for _g, _spec in GARMENTS.items():
    for _syn in _spec.get("synonyms", []):
        _GARMENT_SYNONYMS.setdefault(_syn, _g)
# Plurals of a garment name itself also resolve (a "kurtas" ask still finds "kurta").
for _g in list(GARMENTS):
    if not _g.endswith("s"):
        _GARMENT_SYNONYMS.setdefault(_g + "s", _g)

_KN_GARMENTS: dict[str, str] = {"ಕುರ್ತಾ": "kurta", "ಡ್ರೆಸ್": "dress", "ಶರ್ಟ್": "shirt", "ಜೀನ್ಸ್": "jeans", "ಸೀರೆ": "saree"}

_OCCASION_SYNONYMS: dict[str, str] = {"work": "office", "workwear": "office", "diwali": "festive", "pooja": "festive", "ethnic day": "festive", "sangeet": "wedding", "reception": "wedding", "shaadi": "wedding"}
for _o in OCCASIONS:
    _OCCASION_SYNONYMS.setdefault(_o, _o)

_STOP_WORDS = {"a", "an", "the", "my", "this", "that", "with", "for", "in", "goes", "go", "what", "show", "me", "some", "any", "and", "or", "photo"}


@dataclass
class ParsedGarment:
    garment_type: str | None = None
    role: str | None = None
    colour: str | None = None
    colour_family: str | None = None
    pattern: str | None = None
    occasion: str | None = None
    fabric: str | None = None
    section: str | None = None
    unknown_colour: str | None = None

    def describe(self) -> str:
        bits: list[str] = []
        if self.colour:
            bits.append(self.colour)
        if self.pattern and self.pattern != "solid":
            bits.append(self.pattern)
        noun = self.garment_type or "garment"
        text = f"a {' '.join(bits + [noun])}" if bits else f"a {noun}"
        return text


def _find_colour(low: str) -> tuple[str | None, str | None]:
    """(colour phrase as typed, resolved family) or (None, None)."""
    for phrase in sorted(MULTI_WORD_ALIASES, key=len, reverse=True):
        if phrase in low:
            return phrase, MULTI_WORD_ALIASES[phrase]
    for token in re.findall(r"[a-z]+", low):
        if token in SINGLE_WORD_ALIASES:
            return token, SINGLE_WORD_ALIASES[token]
    for kn, fam in KN_COLOURS.items():
        if kn in low:
            return kn, fam
    return None, None


def _find_garment(low: str) -> str | None:
    # multi-word or hyphenated garment names ("saree blouse", "lehenga set", "t-shirt") first,
    # matched as a substring so "T-Shirt"/"t shirt" both resolve before single-word tokenising
    # would otherwise split "t-shirt" into "t" and "shirt" and match plain "shirt" instead.
    for name in sorted(GARMENTS, key=len, reverse=True):
        if (" " in name or "-" in name) and name in low:
            return name
    for phrase, canon in sorted(_GARMENT_SYNONYMS.items(), key=lambda kv: len(kv[0]), reverse=True):
        if (" " in phrase or "-" in phrase) and phrase in low:
            return canon
    words = re.findall(r"[a-z]+", low)
    for w in words:
        if w in GARMENTS:
            return w
        if w in _GARMENT_SYNONYMS:
            return _GARMENT_SYNONYMS[w]
    for kn, g in _KN_GARMENTS.items():
        if kn in low:
            return g
    return None


def parse_description(text: str) -> ParsedGarment:
    low = text.lower().strip()
    colour_phrase, colour_family = _find_colour(low)
    garment = _find_garment(low)
    role = GARMENTS[garment]["role"] if garment else None

    pattern = next((p for p in PATTERNS if p != "solid" and p in low), None)
    fabric = next((f for f in FABRICS if f in low), None)
    occasion = next((canon for word, canon in _OCCASION_SYNONYMS.items() if word in low), None)
    section = "women" if "women" in low or "womens" in low else ("men" if re.search(r"\bmen\b|\bmens\b", low) else None)

    unknown_colour = None
    if colour_phrase is None and garment:
        words = re.findall(r"[a-z]+", low)
        gwords = garment.split()
        try:
            gi = next(i for i in range(len(words)) if words[i : i + len(gwords)] == gwords)
        except StopIteration:
            gi = None
        if gi is not None and gi > 0:
            candidate = words[gi - 1]
            reserved = _STOP_WORDS | {pattern or ""} | {fabric or ""} | set(_OCCASION_SYNONYMS) | {"women", "mens", "men"}
            if candidate not in reserved and candidate not in _GARMENT_SYNONYMS and candidate not in GARMENTS:
                unknown_colour = candidate
                colour_phrase = candidate

    return ParsedGarment(
        garment_type=garment, role=role, colour=colour_phrase, colour_family=colour_family,
        pattern=pattern, occasion=occasion, fabric=fabric, section=section, unknown_colour=unknown_colour,
    )


__all__ = ["ParsedGarment", "family_of", "parse_description"]
