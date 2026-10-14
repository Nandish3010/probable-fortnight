"""Untrusted free text on its way to a model (P3, adversarial eval, 14 Oct 2026).

SKU display names, store notes and any other free-text field a tool returns can carry text written by
someone other than the operator. The planner and chat prompts are not changed; instead the text is
cleaned in code before a tool hands it to the model (`clean_text`, `clean_tree`), and the guardrail
layer rejects a rationale that copies a run of words from such a field (`copied_run`, used by the
cite_or_drop rule). English patterns only; this is a screen, not a proof (a paraphrase passes).
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any

MAX_LEN = 80
COPY_RUN = 4  # consecutive words copied from an untrusted field that make a rationale invalid

# Cyrillic and Greek look-alikes that NFKC leaves alone (P6 used Cyrillic i/o/e/p/c).
_CONFUSABLE = str.maketrans({"а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "і": "i", "ј": "j", "ѕ": "s", "ԁ": "d", "һ": "h", "ӏ": "l", "ո": "n", "ѵ": "v", "х": "x", "у": "y",
                             "А": "A", "Е": "E", "О": "O", "Р": "P", "С": "C", "І": "I", "Ј": "J", "Ѕ": "S", "Н": "H", "К": "K", "М": "M", "Т": "T", "Х": "X", "ο": "o", "ν": "v", "ι": "i"})

_INSTRUCTION = re.compile(
    r"(ignore|disregard|forget|override)\s+(all\s+|any\s+|the\s+|your\s+|my\s+)*(previous|prior|above|earlier|preceding|existing)?\s*(instruction|rule|polic|prompt|guideline|guardrail)"
    r"|(ignore|disregard)\s+(all\s+|any\s+|the\s+)*(previous|prior|above|earlier)"
    r"|system\s+(prompt|override|message|instruction)"
    r"|you\s+are\s+now\b|from\s+now\s+on\b|new\s+instructions?"
    r"|(set|raise|change|apply|use)\s+(the\s+|a\s+|an\s+)?(discount|markdown|holdout|guardrail|mechanic|coupon)"
    r"|skip\s+(the\s+)?(holdout|guardrail|check|validation|policy)"
    r"|(mark|treat|record)\s+(the\s+|all\s+)*(guardrail|check|rule)s?\b"
    r"|do\s+not\s+(call|run|use|check)\s+(the\s+)?(check_guardrails|guardrail|estimate|propose)"
    r"|(begin|start)\s+(the\s+|your\s+)?(rationale|reply|answer|response)\s+with"
    r"|(reply|respond)\s+(only\s+)?with\s+DONE",
    re.IGNORECASE,
)


def _skeleton(text: str) -> str:
    """Lower-risk form for matching only: NFKC, look-alikes folded, invisible/format characters removed."""
    t = unicodedata.normalize("NFKC", text).translate(_CONFUSABLE)
    return "".join(ch for ch in t if unicodedata.category(ch) not in ("Cf", "Cc", "Cs")).replace("­", "")


def clean_text(text: str, fallback: str) -> str:
    """Control characters and newlines become single spaces, the length is capped at MAX_LEN, and text that
    reads as an instruction to the model is replaced by `fallback` (the SKU id). Idempotent; ordinary
    product names, dates and ids come back unchanged."""
    spaced = "".join(" " if unicodedata.category(ch) in ("Cc", "Zl", "Zp") else ch for ch in text)
    spaced = re.sub("[\u200b\u2060\ufeff\u202a-\u202e\u2066-\u2069]", "", spaced)  # not ZWJ/ZWNJ: Indic scripts need them
    spaced = re.sub(r"[ \t]{2,}", " ", spaced).strip()
    if _INSTRUCTION.search(_skeleton(spaced)) or _INSTRUCTION.search(_skeleton(text)):
        return fallback
    return spaced[:MAX_LEN]


def clean_tree(obj: Any, fallback: str) -> Any:
    """`clean_text` on every string value of a dict/list (keys untouched)."""
    if isinstance(obj, str):
        return clean_text(obj, fallback)
    if isinstance(obj, dict):
        return {k: clean_tree(v, fallback) for k, v in obj.items()}
    if isinstance(obj, list):
        return [clean_tree(v, fallback) for v in obj]
    return obj


def strings_in(obj: Any) -> list[str]:
    if isinstance(obj, str):
        return [obj]
    if isinstance(obj, dict):
        return [s for v in obj.values() for s in strings_in(v)]
    if isinstance(obj, list):
        return [s for v in obj for s in strings_in(v)]
    return []


def _words(text: str) -> list[str]:
    return re.findall(r"\w+", _skeleton(text).lower())


def copied_run(rationale: str, sources: list[str], n: int = COPY_RUN) -> str | None:
    """The first run of `n` consecutive words of `rationale` that also appears, in order, in one of the
    untrusted `sources`; None when there is none."""
    r = _words(rationale)
    grams: dict[tuple[str, ...], str] = {}
    for src in sources:
        w = _words(src)
        for i in range(len(w) - n + 1):
            grams.setdefault(tuple(w[i:i + n]), " ".join(w[i:i + n]))
    for i in range(len(r) - n + 1):
        if (hit := grams.get(tuple(r[i:i + n]))) is not None:
            return hit
    return None
