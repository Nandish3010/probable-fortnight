"""The real-photo vision harness: the privacy pass strips every metadata block, and the scorer and
aggregates are right on known inputs. Stub backend only -- a stub run is never a measurement."""
import json
from pathlib import Path

from PIL import Image

from harness import vision_real_eval as ev
from harness import vision_real_prep as prep


def _phone_photo(path: Path) -> None:
    """A 4000x3000 landscape JPEG tagged as rotated 90 deg, with GPS, device, timestamp and ICC."""
    im = Image.effect_noise((4000, 3000), 40).convert("RGB")
    exif = Image.Exif()
    exif[0x0112] = 6  # Orientation: rotate 90 CW on display
    exif[0x010F] = "PhoneMaker"
    exif[0x0110] = "PhoneModel X"
    exif[0x0132] = "2026:09:25 18:12:04"
    exif[0x8825] = {1: "N", 2: (12.0, 58.0, 0.0), 3: "E", 4: (77.0, 35.0, 0.0)}  # GPS IFD
    im.save(path, "JPEG", quality=95, exif=exif.tobytes(), icc_profile=b"\x00" * 128, comment=b"shot on shelf 3")


def test_prep_strips_all_metadata_applies_orientation_and_limits_size(tmp_path):
    src, out = tmp_path / "src", tmp_path / "out"
    src.mkdir()
    _phone_photo(src / "IMG_20260925_181204.jpg")
    _phone_photo(src / "IMG_20260925_181300.jpg")
    (src / "labels.csv").write_text(
        "file,product_name,best_before_date,units_visible,mrp_inr\n"
        "IMG_20260925_181204.jpg,Masala Chips 200G,2026-11-02,4,20\n"
        "IMG_20260925_181300.jpg,Something Else,2026-10-01,3,\n",
        encoding="utf-8",
    )
    raw = (src / "IMG_20260925_181204.jpg").read_bytes()
    assert b"Exif\x00\x00" in raw and b"ICC_PROFILE" in raw  # the fixture really carries metadata
    res = prep.prepare(src, out, exclude={"IMG_20260925_181300.jpg"})
    assert res == {"kept": 1, "excluded": ["IMG_20260925_181300.jpg"], "dirty": {}}
    written = sorted((out / "photos").iterdir())
    assert [p.name for p in written] == ["photo_01.jpg"]  # the timestamped phone name is gone
    assert prep.audit(written[0]) == []
    with Image.open(written[0]) as im:
        assert im.size == (960, 1280)  # portrait: orientation baked into pixels before EXIF dropped
    assert written[0].stat().st_size <= prep.MAX_BYTES
    labels = json.loads((out / "labels.json").read_text())
    assert labels == [{"file": "photo_01.jpg", "product_name": "Masala Chips 200G", "best_before_date": "2026-11-02", "units_visible": 4, "mrp_inr": 20.0}]
    assert "IMG_" not in (out / "labels.json").read_text()


def test_audit_catches_a_file_that_still_has_exif(tmp_path):
    _phone_photo(tmp_path / "dirty.jpg")
    problems = prep.audit(tmp_path / "dirty.jpg")
    assert any("exif" in p.lower() for p in problems) and any("icc" in p.lower() for p in problems)


def test_product_match_and_percentile():
    assert ev.product_match("Masala Chips 200G", "masala chips 200g") == (True, True)
    assert ev.product_match("Masala Chips", "Masala Chips 200G") == (False, True)
    assert ev.product_match("Salted Chips 200G", "Masala Chips 200G") == (False, False)
    assert ev.percentile([1.0, 2.0, 3.0, 4.0], 50) == 2.0
    assert ev.percentile([float(i) for i in range(1, 21)], 95) == 19.0
    assert ev.percentile([], 50) is None


def test_score_picks_the_label_row_and_sums_units_across_blocks():
    names = {"SKU-A": "Masala Chips 200G", "SKU-B": "Cola 500ML"}
    rows = [
        {"sku_guess": "SKU-B", "sku_confidence": 0.95, "best_before_date": "2026-10-01", "date_confidence": 0.9, "facings_count": 6, "count_confidence": 0.9, "needs_confirmation": False},
        {"sku_guess": "SKU-A", "sku_confidence": 0.8, "best_before_date": "2026-11-02", "date_confidence": 0.9, "facings_count": 2, "count_confidence": 0.9, "needs_confirmation": False},
        {"sku_guess": "SKU-A", "sku_confidence": 0.8, "best_before_date": "2026-11-02", "date_confidence": 0.9, "facings_count": 2, "count_confidence": 0.9, "needs_confirmation": False},
    ]
    label = {"product_name": "Masala Chips 200G", "best_before_date": "2026-11-02", "units_visible": 5, "mrp_inr": 20.0}
    s = ev.score(label, rows, names)
    assert s["predicted_sku"] == "SKU-A" and s["predicted_units"] == 4
    assert s["product_exact"] and s["date_exact"] and not s["units_exact"] and s["units_pm1"]
    assert s["mrp_exact"] is None  # the row has no mrp_inr: not measurable, not "wrong"
    assert s["wrong"] and s["fields_wrong"] == 1 and s["in_catalogue"]


def test_stub_run_end_to_end_is_labelled_not_a_measurement(base_store, tmp_path, monkeypatch):
    d = tmp_path / "run"
    (d / "photos").mkdir(parents=True)
    Image.new("RGB", (64, 48), "white").save(d / "photos" / "photo_01.jpg", "JPEG")
    (d / "labels.json").write_text(json.dumps([{"file": "photo_01.jpg", "product_name": "Masala Chips 200G", "best_before_date": "2026-11-02", "units_visible": 8, "mrp_inr": 20.0}]))
    out = ev.run(d, passes=2, store=base_store, backend="stub")
    s = out["summary"]
    assert s["calls"] == 2 and s["errors"] == 0
    assert s["fields"]["best_before_exact"]["correct"] == 0  # the stub upload read has no date
    assert s["fields"]["mrp_exact"]["n"] == 0 and "not measurable" in s["fields"]["mrp_exact"]["note"]
    assert s["calibration"]["flagged_needs_confirmation"] == {"n": 2, "actually_wrong": 2}
    assert s["consistency"]["photos_identical_across_all_passes"]["correct"] == 1
    md = ev.render({"generated_at": "t", "backend": "stub", "model_id": "stub-vision"}, s, out["worst"])
    assert "NOT A MEASUREMENT" in md
    monkeypatch.setenv("TAAL_MODEL_BACKEND", "stub")
    monkeypatch.setenv("TAAL_DATA_DIR", str(base_store.root))
    assert ev.main(["--dir", str(d), "--passes", "1"]) == 1  # a stub run never exits green
    assert json.loads((d / "results.json").read_text())["meta"]["measurement"] is False
