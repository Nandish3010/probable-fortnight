"""Guards on config/models.toml: the pinned ids must be distinct, current and verified."""
import json
from pathlib import Path

from agents.gate.config import ROOT, load_models

RETIRED = {"gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.5-flash-lite", "gemini-3.6-flash"}


def test_flash_and_fallback_are_distinct_and_not_retired():
    ids = load_models()["ids"]
    assert ids["flash"] != ids["fallback"], "a fallback must be a different model"
    for key in ("flash", "fallback", "flash_lite"):
        assert ids[key] not in RETIRED, f"ids.{key} = {ids[key]} is retired or retiring"


def test_vertex_location_is_a_region_because_bigquery_shares_it():
    assert load_models()["vertex"]["location"] != "global"


def test_every_pinned_id_has_a_200_in_the_committed_verification_evidence():
    models = load_models()
    evidence = sorted((ROOT / "eval" / "raw").glob("model_verification_*.json"))
    assert evidence, "commit eval/raw/model_verification_<date>.json when an id changes"
    matrix = json.loads(Path(evidence[-1]).read_text(encoding="utf-8"))["matrix"]
    location = models["vertex"]["location"]
    for model_id, where in ((models["ids"]["flash"], location), (models["ids"]["fallback"], models["vertex"].get("fallback_location") or location)):
        assert matrix[f"{model_id}@{where}"]["status"] == 200, f"{model_id} was not verified in {where}"
