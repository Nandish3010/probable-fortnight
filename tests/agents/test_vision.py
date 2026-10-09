import json
from pathlib import Path

import jsonschema

from agents.capture.vision import CONFIDENCE_THRESHOLD, SCHEMA, commit_rows, intake
from agents.gate.config import load_models

ROOT = Path(__file__).resolve().parents[2]


def test_staged_photos_validate_and_flag_low_confidence(base_store):
    for f in sorted((ROOT / "fixtures" / "photos").glob("pallet_*.json")):
        d = json.loads(f.read_text())
        res = intake(base_store, d["node_id"], photo_ref=d["photo_ref"])
        jsonschema.validate(res, SCHEMA, format_checker=jsonschema.FormatChecker())
        for r in res["rows"]:
            low = min(r["sku_confidence"], r["date_confidence"], r["count_confidence"]) < CONFIDENCE_THRESHOLD or r["best_before_date"] is None
            assert r["needs_confirmation"] == low
            if low:
                assert r["confirmation_question"]
        if any(r["date_confidence"] < CONFIDENCE_THRESHOLD for r in res["rows"]):
            assert res["pass"] == "two_pass"


def test_model_id_matches_config_in_vertex_mode_and_is_labelled_in_stub(base_store):
    res = intake(base_store, "DS-07", photo_ref="fixtures/photos/pallet_lowconf_test.jpg", backend="stub")
    assert res["model_id"] == "stub-vision"
    assert load_models()["ids"]["flash"]  # the vertex branch uses this id; exercised only with credentials


def test_commit_writes_photo_batches_with_derived_sellby(sandbox):
    res = intake(sandbox, "DS-07", photo_ref="fixtures/photos/pallet_lowconf_test.jpg")
    result = commit_rows(sandbox, "DS-07", res["rows"], res["photo_ref"], "2026-09-12T09:00:00Z")
    assert len(result["written"]) == 2  # the low-confidence row was not confirmed
    assert result["skipped"] == [{"sku_guess": res["rows"][2]["sku_guess"], "reason": "not confirmed"}]
    for b in result["written"]:
        assert b["source"] == "photo" and b["capture_ref"] == res["photo_ref"] and b["online_sellby_date"] <= b["expiry_date"]
    res["rows"][2]["confirmed"] = True
    result2 = commit_rows(sandbox, "DS-07", res["rows"], res["photo_ref"], "2026-09-12T09:00:00Z")
    assert len(result2["written"]) == 3 and result2["skipped"] == []


def test_uploaded_photo_with_no_date_is_skipped_with_a_reason_not_silently_dropped(sandbox):
    """The stub returns null-date rows for an uploaded photo by design, to exercise the
    confirmation flow -- exactly what happens in vertex mode whenever Gemini cannot read a
    printed date. Confirming such a row must not report success while writing nothing."""
    res = intake(sandbox, "DS-07", image_data_url="data:image/png;base64,x")
    for row in res["rows"]:
        row["confirmed"] = True
    result = commit_rows(sandbox, "DS-07", res["rows"], res["photo_ref"], "2026-09-12T09:00:00Z")
    assert result["written"] == []
    assert result["skipped"] and all(s["reason"] == "no best_before_date" for s in result["skipped"])


def test_supplying_a_hand_entered_date_commits_the_row(sandbox):
    """The operator's fix for an unreadable date: fill it in by hand, then it commits like any
    other confirmed row."""
    res = intake(sandbox, "DS-07", image_data_url="data:image/png;base64,x")
    for row in res["rows"]:
        row["confirmed"] = True
        row["best_before_date"] = "2026-12-01"
    result = commit_rows(sandbox, "DS-07", res["rows"], res["photo_ref"], "2026-09-12T09:00:00Z")
    assert len(result["written"]) == len(res["rows"]) and result["skipped"] == []
    assert all(b["expiry_date"] == "2026-12-01" for b in result["written"])


def _gallery_refs():
    """The photo_refs the phone view offers as samples (web/app/phone/page.tsx SAMPLE_PHOTOS)."""
    import re

    page = (ROOT / "web" / "app" / "phone" / "page.tsx").read_text(encoding="utf-8")
    return re.findall(r'ref: "(fixtures/photos/pallet_\d+\.jpg)"', page)


def test_the_phone_gallery_has_a_sample_with_a_row_under_the_threshold(base_store):
    refs = _gallery_refs()
    assert len(refs) >= 7
    low = [r for r in refs if any(row["needs_confirmation"] for row in intake(base_store, "DS-07", photo_ref=r, backend="stub")["rows"])]
    assert "fixtures/photos/pallet_06.jpg" in low  # the one labelled "date hard to read"
    assert "fixtures/photos/pallet_01.jpg" not in low  # the first sample reads clean


def test_pallet_06_routes_its_unclear_row_to_confirm_and_holds_it_back_until_answered(sandbox):
    res = intake(sandbox, "DS-07", photo_ref="fixtures/photos/pallet_06.jpg", backend="stub")
    clear, unclear = res["rows"]
    assert (clear["needs_confirmation"], unclear["needs_confirmation"]) == (False, True)
    assert min(unclear["sku_confidence"], unclear["date_confidence"], unclear["count_confidence"]) < CONFIDENCE_THRESHOLD <= min(clear["sku_confidence"], clear["date_confidence"], clear["count_confidence"])
    assert "Poha" in unclear["confirmation_question"] and res["pass"] == "two_pass"

    held = commit_rows(sandbox, "DS-07", res["rows"], res["photo_ref"], "2026-09-12T09:00:00Z")
    assert [b["sku"] for b in held["written"]] == [clear["sku_guess"]]
    assert held["skipped"] == [{"sku_guess": unclear["sku_guess"], "reason": "not confirmed"}]
    unclear["confirmed"] = True
    both = commit_rows(sandbox, "DS-07", res["rows"], res["photo_ref"], "2026-09-12T09:00:00Z")
    assert len(both["written"]) == 2 and both["skipped"] == []

