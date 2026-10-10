"""API behaviour during a model outage and /health's fallback field. Gemini is faked
(tests/fake_gemini.py); the vertex backend is selected by environment only for these tests."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from tests.fake_gemini import (
    FALLBACK,
    PRIMARY,
    FakeGemini,
    FakeGenaiClient,
    pin_models,
    vertex_environment,
)

H = {"X-Taal-Visitor": "v-outage", "Origin": "http://localhost:3000"}
JSON = {**H, "Accept": "application/json"}


@pytest.fixture
def client(data_dir, tmp_path, monkeypatch):
    monkeypatch.setenv("TAAL_DATA_DIR", str(data_dir))
    monkeypatch.setenv("TAAL_SANDBOX_DIR", str(tmp_path / "sandbox"))
    as_of = json.loads((data_dir / "manifest.json").read_text())["as_of"]
    monkeypatch.setenv("TAAL_NOW", f"{as_of}T03:30:00Z")
    monkeypatch.setenv("TAAL_MODEL_BACKEND", "vertex")
    pin_models(monkeypatch)
    vertex_environment(monkeypatch)
    from agents.customer.chat import reset_sessions
    from services.api.main import app

    reset_sessions()
    return TestClient(app)


def test_chat_503_is_structured_retryable_and_readable_by_the_browser(client, monkeypatch):
    FakeGemini({PRIMARY: 404, FALLBACK: 503}).install(monkeypatch)
    r = client.post("/chat", json={"session_id": "CUST-MEENA:web", "text": "hi"}, headers=JSON)
    assert r.status_code == 503
    assert r.json() == {"error": "model_unavailable", "model": PRIMARY, "retry_after_s": 30}
    assert r.headers["retry-after"] == "30"
    assert r.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_chat_survives_a_retired_primary(client, monkeypatch):
    FakeGemini({PRIMARY: 404, FALLBACK: '{"text": "Served by the fallback"}'}).install(monkeypatch)
    r = client.post("/chat", json={"session_id": "CUST-MEENA:web", "text": "hi"}, headers=JSON)
    assert r.status_code == 200 and r.json()[0]["text"] == "Served by the fallback"


def test_capture_503_and_fallback(client, monkeypatch):
    body = {"node_id": "DS-07", "image_data_url": "data:image/png;base64,AAAA"}
    FakeGenaiClient({PRIMARY: 500, FALLBACK: 404}).install(monkeypatch)
    r = client.post("/capture", json=body, headers=H)
    assert r.status_code == 503 and r.json()["error"] == "model_unavailable"
    rows = {"rows": [{"sku_guess": "SKU-MASALA-CHIPS-200G", "sku_confidence": 0.9, "best_before_date": "2026-12-01", "date_confidence": 0.9, "facings_count": 6, "count_confidence": 0.9}]}
    FakeGenaiClient({PRIMARY: 404, FALLBACK: rows}).install(monkeypatch)
    ok = client.post("/capture", json=body, headers=H)
    assert ok.status_code == 200 and ok.json()["model_id"] == FALLBACK


def test_plan_during_an_outage_returns_the_deterministic_draft_not_an_error(client, monkeypatch):
    FakeGemini({PRIMARY: 503, FALLBACK: 503}).install(monkeypatch)
    r = client.post("/plan", json={"gap_id": "gap_tea_ds04"}, headers=H)
    assert r.status_code == 200 and r.json()["plan_source"] == "deterministic_rules"


def test_health_names_the_fallback(client):
    d = client.get("/health", headers=H).json()
    assert d["model_fallback"] == FALLBACK and d["checks"]["vertex"]["detail"]
    assert PRIMARY not in d["checks"]["vertex"]["detail"] or "fallback" in d["checks"]["vertex"]["detail"]


def test_health_fallback_is_null_without_one(client, monkeypatch):
    pin_models(monkeypatch, fallback=None)
    assert client.get("/health", headers=H).json()["model_fallback"] is None
