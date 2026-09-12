"""docs/openapi.yaml is generated from the FastAPI app (make openapi); CI fails on drift."""
from pathlib import Path

import yaml

from services.api.main import app

ROOT = Path(__file__).resolve().parents[2]


def test_openapi_yaml_matches_app():
    doc = yaml.safe_load((ROOT / "docs" / "openapi.yaml").read_text())
    live = app.openapi()
    assert set(doc["paths"]) == set(live["paths"]), "run `make openapi` and commit docs/openapi.yaml"
    for path, ops in live["paths"].items():
        assert set(ops) == set(doc["paths"][path]), path


def test_required_routes_exist():
    paths = set(app.openapi()["paths"])
    for p in ("/health", "/approve", "/rerun", "/events/{run_id}", "/events/{run_id}/stream", "/chat", "/reset", "/capture", "/gaps", "/plays", "/plays/{play_id}", "/outcomes", "/execution", "/policy"):
        assert p in paths, p
