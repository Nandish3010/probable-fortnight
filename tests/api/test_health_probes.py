"""/health "sessions" and "firestore": honest when a flag is off (no probe), a bounded probe when
it is on, cached for 60 s. Fakes stand in for the Agent Engine and Firestore (no network)."""
import asyncio
import json
import time

import pytest
from fastapi.testclient import TestClient

from agents.gate import firestore_cache as fc
from agents.gate.config import load_tenant
from agents.gate.firestore_cache import FirestoreCache
from services.api import health_probes
from tests.fake_firestore import FakeClient

H = {"X-Taal-Visitor": "v-health-probe"}


@pytest.fixture
def client(data_dir, tmp_path, monkeypatch):
    monkeypatch.setenv("TAAL_DATA_DIR", str(data_dir))
    monkeypatch.setenv("TAAL_SANDBOX_DIR", str(tmp_path / "sandbox"))
    as_of = json.loads((data_dir / "manifest.json").read_text())["as_of"]
    monkeypatch.setenv("TAAL_NOW", f"{as_of}T03:30:00Z")
    monkeypatch.delenv("TAAL_SESSION_BACKEND", raising=False)
    monkeypatch.delenv("TAAL_SERVING_CACHE", raising=False)
    health_probes.reset_probe_cache()
    fc.STATS.reset()
    from services.api.main import app

    yield TestClient(app)
    health_probes.reset_probe_cache()


def _checks(client):
    r = client.get("/health", headers=H)
    assert r.status_code == 200
    return r.json()["checks"]


def test_flags_off_report_the_local_backends_and_run_no_probe(client):
    c = _checks(client)
    assert c["sessions"]["ok"] and c["sessions"]["backend"] == "in_memory" and "probe" not in c["sessions"]
    assert "restart forgets" in c["sessions"]["detail"]
    assert c["firestore"]["ok"] and c["firestore"]["backend"] == "local_store" and "probe" not in c["firestore"]
    assert "serving cache off" in c["firestore"]["detail"]


def test_firestore_on_with_a_current_mirror(client, data_dir, monkeypatch):
    monkeypatch.setenv("TAAL_SERVING_CACHE", "firestore")
    fake = FakeClient()
    tenant = load_tenant().tenant_id
    fc.mirror(data_dir, FirestoreCache(fake, tenant))
    monkeypatch.setattr(fc, "build_cache", lambda tenant_id=None, project=None: FirestoreCache(fake, tenant_id or tenant))
    c = _checks(client)["firestore"]
    assert c["ok"] and c["backend"] == "firestore" and c["mirror_current"] is True
    assert c["mirror"]["snapshot_id"] == c["serving_snapshot_id"] and c["probe_cached"] is False
    reads = fake.reads
    assert _checks(client)["firestore"]["probe_cached"] is True and fake.reads == reads, "a second /health within 60 s must not re-probe"


def test_firestore_on_without_a_mirror_is_not_ok(client, monkeypatch):
    monkeypatch.setenv("TAAL_SERVING_CACHE", "firestore")
    fake = FakeClient()
    monkeypatch.setattr(fc, "build_cache", lambda tenant_id=None, project=None: FirestoreCache(fake, tenant_id or "kutumb-mart"))
    c = _checks(client)["firestore"]
    assert c["ok"] is False and "no mirror" in c["probe"]


class _SlowSessions:
    async def get_session(self, **kw):
        await asyncio.sleep(3)


class _OkSessions:
    async def get_session(self, **kw):
        return None


def test_sessions_on_probe_ok(client, monkeypatch):
    monkeypatch.setenv("TAAL_SESSION_BACKEND", "vertex")
    monkeypatch.setenv("TAAL_AGENT_ENGINE_ID", "1234")
    monkeypatch.setattr("agents.vertex_sessions.build_session_service", lambda *a, **k: _OkSessions())
    c = _checks(client)["sessions"]
    assert c["ok"] and c["backend"] == "vertex_ai_sessions" and c["agent_engine_id"] == "1234"


def test_sessions_probe_is_bounded_at_one_second(client, monkeypatch):
    monkeypatch.setenv("TAAL_SESSION_BACKEND", "vertex")
    monkeypatch.setenv("TAAL_AGENT_ENGINE_ID", "1234")
    monkeypatch.setattr("agents.vertex_sessions.build_session_service", lambda *a, **k: _SlowSessions())
    t0 = time.perf_counter()
    c = _checks(client)["sessions"]
    assert time.perf_counter() - t0 < 2.5
    assert c["ok"] is False and "timed out" in c["probe"]
