"""V3 / V6 regression (adversarial eval, 14 Oct 2026): deterministic post-processing of a LIVE vision read.
Fixtures are the recorded model outputs of V3 (photo of a screen, 3 rows at confidence 1.0, 500/320/240
facings) and V6 (invented SKU-MILK-BREAD-400G). Recorded replays (staged pallets) never pass through the gate."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from agents.capture import vision

RAW = Path(__file__).resolve().parents[2] / "eval" / "raw" / "adversarial_2026-10-14" / "vision"


def _live(monkeypatch, store, rows):
    monkeypatch.setattr(vision, "_vertex_rows", lambda *a, **k: {"photo_ref": "upload", "node_id": "DS-07", "rows": [dict(r) for r in rows], "model_id": "gemini-3.5-flash"})
    return vision.intake(store, "DS-07", image_data_url="data:image/jpeg;base64,AAAA", backend="vertex")


def _recorded(name):
    rows = json.loads((RAW / name).read_text())["output"]["rows"]
    return [{k: v for k, v in r.items() if k not in ("needs_confirmation", "confirmation_question")} for r in rows]


def test_v3_screen_table_is_routed_to_a_human(monkeypatch, base_store):
    res = _live(monkeypatch, base_store, _recorded("V3-screen-stock-table__run1.json"))
    assert res["rows"] and all(r["needs_confirmation"] for r in res["rows"])
    assert all("Check:" in r["confirmation_question"] for r in res["rows"])


def test_facings_cap_flags_even_with_mixed_confidence(monkeypatch, base_store):
    row = {"sku_guess": "SKU-NACHOS-200G", "sku_confidence": 0.95, "best_before_date": "2026-10-12", "date_confidence": 0.99, "facings_count": 61, "count_confidence": 0.9}
    assert _live(monkeypatch, base_store, [row])["rows"][0]["needs_confirmation"]
    assert not _live(monkeypatch, base_store, [{**row, "facings_count": 60}])["rows"][0]["needs_confirmation"]


def test_v6_invented_sku_outside_the_catalogue_is_dropped(monkeypatch, base_store):
    row = {"sku_guess": "SKU-DOES-NOT-EXIST-1KG", "sku_confidence": 0.9, "best_before_date": "2026-10-12", "date_confidence": 0.99, "facings_count": 3, "count_confidence": 0.9}
    assert _live(monkeypatch, base_store, [row])["rows"] == []


def test_v6_recorded_guess_is_dropped(monkeypatch, base_store):
    """16 Oct follow-up: SKU-MILK-BREAD-400G is a real catalogue SKU but was read at sku_confidence 0.4, a guess,
    so the row is dropped on a live read (zero rows passes the pre-registered V6 criterion)."""
    res = _live(monkeypatch, base_store, _recorded("V6-rotated-cropped-label__run1.json"))
    assert res["rows"] == []


def test_sku_below_the_floor_is_dropped_and_just_above_is_flagged(monkeypatch, base_store):
    row = {"sku_guess": "SKU-NACHOS-200G", "sku_confidence": 0.2, "best_before_date": "2026-10-12", "date_confidence": 0.99, "facings_count": 5, "count_confidence": 0.99}
    assert _live(monkeypatch, base_store, [row])["rows"] == []
    assert _live(monkeypatch, base_store, [{**row, "sku_confidence": 0.45}])["rows"] == []
    kept = _live(monkeypatch, base_store, [{**row, "sku_confidence": 0.55}])["rows"]
    assert len(kept) == 1 and kept[0]["needs_confirmation"]


@pytest.mark.parametrize("name", ["VC1-control-nachos__run1.json", "VC2-control-pallet-01__run1.json"])
def test_real_live_controls_stay_unflagged(monkeypatch, base_store, name):
    res = _live(monkeypatch, base_store, _recorded(name))
    assert res["rows"] and not any(r["needs_confirmation"] for r in res["rows"])


@pytest.mark.parametrize("pallet", ["pallet_01", "pallet_02", "pallet_03", "pallet_04", "pallet_05", "pallet_06", "pallet_08", "pallet_lowconf_test"])
def test_recorded_replays_are_byte_identical_and_would_pass_the_gate_anyway(base_store, pallet):
    """The staged pallets are replayed with backend=vertex or stub through the unchanged recorded path,
    and the new gate would not flag any row that the old annotate left unflagged."""
    fixture = json.loads((vision.FIXTURES / f"{pallet}.json").read_text())["rows"]
    for backend in ("stub", "vertex"):
        res = vision.intake(base_store, "DS-07", photo_ref=f"fixtures/photos/{pallet}.jpg", backend=backend)
        before = [r["needs_confirmation"] for r in res["rows"]]
        import copy
        probe = copy.deepcopy(res)
        vision.flag_implausible(probe, {})
        assert [r["needs_confirmation"] for r in probe["rows"]] == before
        core = ("sku_guess", "sku_confidence", "best_before_date", "date_confidence", "facings_count", "count_confidence")
        assert [{k: r[k] for k in core} for r in res["rows"]] == [{k: r[k] for k in core} for r in fixture]


def test_synthetic_photo_reads_would_not_be_flagged():
    """30 recorded synthetic reads: 11 have one row with date confidence 1.0, but largest facings is 6."""
    d = json.loads((Path(__file__).resolve().parents[2] / "eval" / "raw" / "vision_synthetic_2026-09-21.json").read_text())
    assert max(x["predicted_facings"] for x in d) <= vision.MAX_PLAUSIBLE_FACINGS
