"""Garment and skin-tone photo reads (agents/stylist/vision.py). Same shape as
tests/agents/test_vision.py for the grocery pallet-photo intake: a stub read per fixture,
validated against its schema; no store or filesystem writes happen inside the module itself."""
import base64
import inspect
import json
from pathlib import Path

import jsonschema

from agents.stylist import vision
from agents.stylist.vision import (
    GARMENT_SCHEMA,
    SKIN_TONE_SCHEMA,
    describe_garment_photo,
    read_skin_tone,
)

ROOT = Path(__file__).resolve().parents[2]
GARMENTS_DIR = ROOT / "fixtures" / "photos" / "garments"
SELFIES_DIR = ROOT / "fixtures" / "photos" / "selfies"


def _data_url(png_path: Path) -> str:
    return "data:image/png;base64," + base64.b64encode(png_path.read_bytes()).decode()


def test_every_garment_fixture_validates_via_photo_ref_and_data_url():
    for json_path in sorted(GARMENTS_DIR.glob("*.json")):
        recorded = json.loads(json_path.read_text(encoding="utf-8"))
        by_ref = describe_garment_photo(photo_ref=str(json_path))
        jsonschema.validate(by_ref, GARMENT_SCHEMA, format_checker=jsonschema.FormatChecker())
        assert by_ref["garment_type"] == recorded["garment_type"]
        assert by_ref["confidence"] == recorded["confidence"]
        assert by_ref["needs_confirmation"] == (recorded["confidence"] < 0.7)

        png = json_path.with_suffix(".png")
        by_url = describe_garment_photo(image_data_url=_data_url(png))
        jsonschema.validate(by_url, GARMENT_SCHEMA, format_checker=jsonschema.FormatChecker())
        assert by_url["garment_type"] == recorded["garment_type"]


def test_unknown_garment_upload_returns_nulls_and_needs_confirmation():
    r = describe_garment_photo(image_data_url="data:image/png;base64,AAAAAAAA")
    assert r["garment_type"] is None and r["colour_family"] is None
    assert r["needs_confirmation"] is True
    assert r["model_id"] == "stub-vision"


def test_every_selfie_fixture_validates_and_always_needs_confirmation():
    for json_path in sorted(SELFIES_DIR.glob("*.json")):
        recorded = json.loads(json_path.read_text(encoding="utf-8"))
        by_ref = read_skin_tone(photo_ref=str(json_path))
        jsonschema.validate(by_ref, SKIN_TONE_SCHEMA, format_checker=jsonschema.FormatChecker())
        assert by_ref["undertone"] == recorded["undertone"]
        assert by_ref["depth"] == recorded["depth"]
        assert by_ref["needs_confirmation"] is True

        png = json_path.with_suffix(".png")
        by_url = read_skin_tone(image_data_url=_data_url(png))
        jsonschema.validate(by_url, SKIN_TONE_SCHEMA, format_checker=jsonschema.FormatChecker())
        assert by_url["undertone"] == recorded["undertone"]


def test_unclear_selfie_gives_nulls():
    r = read_skin_tone(photo_ref=str(SELFIES_DIR / "unclear.json"))
    assert r["undertone"] is None and r["depth"] is None
    assert r["model_id"] == "stub-vision"


def test_module_never_writes_to_a_store_or_the_filesystem():
    """This module takes no store argument and must never call store.write/append, or open() a
    file for writing; the image bytes must never be persisted anywhere it can reach."""
    source = inspect.getsource(vision)
    assert "store." not in source
    assert re_no_write_open(source)


def re_no_write_open(source: str) -> bool:
    import re

    for m in re.finditer(r"open\(([^)]*)\)", source):
        args = m.group(1)
        assert "'w'" not in args and '"w"' not in args, args
    return True
