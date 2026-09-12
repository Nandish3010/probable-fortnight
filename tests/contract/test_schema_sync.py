"""play.schema.json is the source of truth; the Pydantic models and the TypeScript types mirror it."""
import json
import re
from pathlib import Path

import jsonschema
import pytest
from pydantic import ValidationError

from agents.gate.models import GUARDRAIL_RULES, MECHANICS, Gap, Play

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads((ROOT / "docs" / "schemas" / "play.schema.json").read_text())
GAP_SCHEMA = json.loads((ROOT / "docs" / "schemas" / "gap.schema.json").read_text())
TS = (ROOT / "web" / "lib" / "types.ts").read_text()


def test_schemas_are_valid_2020_12():
    for f in (ROOT / "docs" / "schemas").rglob("*.schema.json"):
        jsonschema.Draft202012Validator.check_schema(json.loads(f.read_text()))


def test_enums_match_between_schema_and_models():
    assert tuple(SCHEMA["properties"]["mechanic"]["enum"]) == MECHANICS
    assert tuple(SCHEMA["properties"]["guardrails"]["items"]["properties"]["rule"]["enum"]) == GUARDRAIL_RULES


def test_top_level_fields_match_pydantic_and_typescript():
    schema_fields = set(SCHEMA["properties"])
    model_fields = set(Play.model_fields)
    assert schema_fields == model_fields
    ts_play = re.search(r"export interface Play \{(.*?)\n\}", TS, re.S).group(1)
    ts_fields = set(re.findall(r"^\s+(\w+)\??:", ts_play, re.M))
    assert schema_fields == ts_fields
    assert set(SCHEMA["required"]) == {k for k, f in Play.model_fields.items() if f.is_required()}


def test_gap_fields_match():
    assert set(GAP_SCHEMA["properties"]) == set(Gap.model_fields)
    ts_gap = re.search(r"export interface Gap \{(.*?)\n\}", TS, re.S).group(1)
    assert set(GAP_SCHEMA["properties"]) == set(re.findall(r"^\s+(\w+)\??:", ts_gap, re.M))


@pytest.mark.parametrize("path", sorted((ROOT / "fixtures" / "plays" / "valid").glob("*.json")))
def test_valid_fixtures_pass_both_validators(path: Path):
    play = json.loads(path.read_text())
    jsonschema.Draft202012Validator(SCHEMA, format_checker=jsonschema.FormatChecker()).validate(play)
    Play.model_validate(play)


@pytest.mark.parametrize("path", sorted((ROOT / "fixtures" / "plays" / "invalid").glob("*.json")))
def test_invalid_fixtures_fail_both_validators(path: Path):
    doc = json.loads(path.read_text())
    play = doc["play"]
    v = jsonschema.Draft202012Validator(SCHEMA, format_checker=jsonschema.FormatChecker())
    assert not v.is_valid(play), doc["mutation"]
    with pytest.raises(ValidationError):
        Play.model_validate(play)


def test_fixture_counts():
    assert len(list((ROOT / "fixtures" / "plays" / "valid").glob("*.json"))) >= 20
    assert len(list((ROOT / "fixtures" / "plays" / "invalid").glob("*.json"))) >= 20
