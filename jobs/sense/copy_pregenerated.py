"""Offer copy generated ahead of time with BigQuery AI.GENERATE_TABLE and stored in a committed
fixture (fixtures/copy_pregenerated.json, written by harness/pregenerate_copy.py).

Why: the approve-time BigQuery call takes about 3.5 to 4 s warm and the approve path caps it at
3 s (services/api/approve.py::COPY_BUDGET_S), so a live approve almost always fell back to the
templated copy. A play that already carries valid copy skips that call in approve(), so the
seeded demo plays are given their BigQuery copy at seed time instead.

An entry is used only while the play still matches the one it was generated for (the
fingerprint: sku, mechanic and its parameters, segments, languages and the best-before date) and
every stored variant still passes validate_copy. Anything else keeps the templated path. No
generated text is ever edited by hand: the fixture is written only by the generation script.
"""
from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from jobs.sense.copy import validate_copy

FIXTURE_PATH = Path(__file__).resolve().parents[2] / "fixtures" / "copy_pregenerated.json"
PROVENANCE = "bigquery_pregenerated"
METHOD = "BigQuery AI.GENERATE_TABLE, pre-generated; reused at approve"


def fingerprint(play: dict[str, Any], best_before: str | None) -> str:
    """A stable hash of everything the generated text depends on."""
    basis = {
        "sku": play["target"]["sku"], "mechanic": play["mechanic"], "mechanic_params": play.get("mechanic_params") or {},
        "segment_ids": list(play["audience"]["segment_ids"]), "language_set": list(play["copy"]["language_set"]), "best_before": best_before,
    }
    return hashlib.sha256(json.dumps(basis, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:16]


@lru_cache(maxsize=4)
def _read(path: str) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def load_fixture(path: str | Path | None = None) -> dict[str, Any]:
    """The fixture keyed by play_id; empty when the file is absent or unreadable."""
    return _read(str(path or FIXTURE_PATH))


def clear_cache() -> None:
    _read.cache_clear()


def pregenerated_variants(play: dict[str, Any], best_before: str | None, fixture: dict[str, Any] | None = None) -> list[dict[str, Any]] | None:
    """The pre-generated variants for `play`, or None when there is no entry, the play no longer
    matches the one the entry was generated for, or any variant fails validate_copy."""
    entry = (load_fixture() if fixture is None else fixture).get(play.get("play_id"))
    if not isinstance(entry, dict) or entry.get("fingerprint") != fingerprint(play, best_before):
        return None
    variants = entry.get("variants") or []
    accepted, reasons = validate_copy(variants, play, best_before)
    if not variants or reasons or len(accepted) != len(variants):
        return None
    return [dict(v) for v in variants]


def provenance_of(play: dict[str, Any], best_before: str | None, variants: list[dict[str, Any]], fixture: dict[str, Any] | None = None) -> str | None:
    """PROVENANCE when `variants` are exactly the stored pre-generated ones for `play`, else None."""
    stored = pregenerated_variants(play, best_before, fixture)
    return PROVENANCE if stored is not None and stored == list(variants) else None
