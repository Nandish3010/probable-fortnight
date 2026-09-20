"""API contract and judge-mode flows against the FastAPI app with per-visitor sandboxes."""
import json
import os

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(data_dir, tmp_path, monkeypatch):
    monkeypatch.setenv("TAAL_DATA_DIR", str(data_dir))
    monkeypatch.setenv("TAAL_SANDBOX_DIR", str(tmp_path / "sandbox"))
    from agents.customer.chat import reset_sessions
    from agents.stylist.chat import reset_sessions as reset_stylist_sessions
    from services.api.main import app

    reset_sessions()
    reset_stylist_sessions()
    return TestClient(app)


def _h(vid):
    return {"X-Taal-Visitor": vid}


def test_health_shape(client):
    r = client.get("/health", headers=_h("v-health"))
    assert r.status_code == 200
    d = r.json()
    assert d["status"] in ("ok", "degraded") and set(d["checks"]) == {"bigquery", "firestore", "vertex", "sessions"}
    assert d["tenant"]["skus"] == 300 and d["tenant"]["nodes"] == 16


def test_gaps_and_plays(client):
    g = client.get("/gaps", params={"node_id": "DS-07"}, headers=_h("visitor-1")).json()
    assert any(x["gap_id"] == "gap_chips_ds07" for x in g)
    assert g == sorted(g, key=lambda x: (-x["rupees_at_stake"], x["gap_id"]))
    p = client.get("/plays", params={"gap_id": "gap_chips_ds07"}, headers=_h("visitor-1")).json()
    assert p and p[0]["play_id"] == "play_chips_ds07_v1" and p[0]["status"] == "proposed"
    assert client.get("/plays/nope", headers=_h("visitor-1")).status_code == 404


def test_approve_is_idempotent_and_moves_the_forecast(client):
    r = client.post("/approve", json={"play_id": "play_chips_ds07_v1"}, headers=_h("v-approve"))
    assert r.status_code == 200
    a = r.json()
    assert a["status"] == "approved" and a["assignment"]["holdout_n"] >= 1 and a["source"] == "live"
    s = a["forecast"]["series"]
    inside = [p for p in s if a["forecast"]["play_window"]["start"][:10] <= p["date"] <= a["forecast"]["play_window"]["end"][:10]]
    outside = [p for p in s if p["date"] > a["forecast"]["play_window"]["end"][:10]]
    assert all(p["play_p50"] > p["baseline_p50"] for p in inside) and all(abs(p["play_p50"] - p["baseline_p50"]) < 1e-6 for p in outside)
    assert a["forecast"]["writeoff_after_inr"] < a["forecast"]["writeoff_before_inr"]
    assert a["forecast"]["latency_ms"] < 15000
    b = client.post("/approve", json={"play_id": "play_chips_ds07_v1"}, headers=_h("v-approve")).json()
    assert "already approved" in b["note"] and b["source"] == "recorded"
    assert b["assignment"] == a["assignment"]


def test_two_visitors_are_isolated_and_reset_is_scoped(client):
    client.post("/approve", json={"play_id": "play_chips_ds07_v1"}, headers=_h("visitor-a"))
    assert client.get("/plays/play_chips_ds07_v1", headers=_h("visitor-a")).json()["status"] == "approved"
    assert client.get("/plays/play_chips_ds07_v1", headers=_h("visitor-b")).json()["status"] == "proposed"
    r = client.post("/reset", headers=_h("visitor-a")).json()
    assert r["ok"] and r["namespace"] == "visitor-a"
    assert client.get("/plays/play_chips_ds07_v1", headers=_h("visitor-a")).json()["status"] == "proposed"
    assert not client.post("/reset").json()["ok"], "no visitor id: base tenant never reset"


def test_chat_sse_and_json(client):
    client.post("/approve", json={"play_id": "play_chips_ds07_v1"}, headers=_h("v-chat"))
    r = client.post("/chat", json={"session_id": "CUST-MEENA:web", "text": "Any offers today?"}, headers=_h("v-chat"))
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    frames = [json.loads(line[5:]) for line in r.text.splitlines() if line.startswith("data:")]
    assert frames and "ಬಳಕೆಗೆ ಉತ್ತಮ" in frames[0]["text"] and frames[0]["latency_ms"] >= 0
    r2 = client.post("/chat", json={"session_id": "CUST-MEENA:web", "text": "Do you have Cola Zero?"}, headers={**_h("v-chat"), "Accept": "application/json"})
    env = r2.json()[0]
    assert env["list"]["rows"] and len(env["list"]["rows"]) <= 10
    assert client.post("/chat", json={"session_id": "bad session", "text": "x"}, headers=_h("v-chat")).status_code == 422


def test_rerun_with_policy_and_events(client):
    v2 = open(os.path.join(os.path.dirname(__file__), "..", "..", "fixtures", "policy_v2.txt")).read()
    r = client.post("/rerun", json={"gap_id": "gap_tea_ds04", "policy_text": v2, "policy_version": "v2"}, headers=_h("v-rerun")).json()
    assert r["play"]["policy_version"] == "v2" and r["source"] == "live"
    ev = client.get(f"/events/{r['run_id']}", headers=_h("v-rerun")).json()
    assert ev["events"] and ev["events"][0]["author"] == "cost_governor" and all("ts_offset_ms" in e for e in ev["events"])
    assert client.get("/policy", headers=_h("v-rerun")).json()["policy_version"] == "v2"
    assert client.get("/events/does-not-exist", headers=_h("v-rerun")).status_code == 404


def test_capture_confirm_and_execution(client):
    cap = client.post("/capture", json={"node_id": "DS-07", "photo_ref": "fixtures/photos/pallet_01.jpg"}, headers=_h("v-cap")).json()
    assert cap["model_id"] and len(cap["rows"]) == 3
    low = [r for r in cap["rows"] if r["needs_confirmation"]]
    assert low and all(r["confirmation_question"] for r in low)
    written = client.post("/capture/confirm", json={"node_id": "DS-07", "photo_ref": cap["photo_ref"], "rows": cap["rows"]}, headers=_h("v-cap")).json()
    assert written["written"] == 2, "unconfirmed low-confidence row must not be written"
    assert all(b["source"] == "photo" and b["online_sellby_date"] <= b["expiry_date"] for b in written["batches"])
    up = client.post("/capture", json={"node_id": "DS-07", "image_data_url": "data:image/jpeg;base64,AAAA"}, headers=_h("v-cap")).json()
    assert all(r["needs_confirmation"] for r in up["rows"])
    ex = client.post("/execution", json={"play_id": "play_chips_ds07_v1", "node_id": "DS-07", "steps_done": ["print_tag"]}, headers=_h("v-cap")).json()
    assert ex["ok"] and ex["execution_id"].startswith("exec_")


def test_outcomes_never_show_a_lift_when_unmeasured(client):
    client.post("/approve", json={"play_id": "play_kaju_ds03_v1"}, headers=_h("v-out"))
    client.post("/measure", headers=_h("v-out"))
    outs = client.get("/outcomes", headers=_h("v-out")).json()
    assert outs
    for o in outs:
        if o["status"] == "unmeasured":
            assert "lift" not in o
        assert o["data_label"] in ("REAL PILOT", "SYNTHETIC")


def test_customers_demo_includes_a_real_holdout_customer(client):
    out = client.get("/customers/demo", params={"play_id": "play_chips_ds07_v1"}, headers=_h("v-cust")).json()
    ids = {c["customer_id"]: c for c in out}
    assert "CUST-MEENA" in ids and ids["CUST-MEENA"]["home_node_id"] == "DS-07" and ids["CUST-MEENA"]["language"] == "kn"
    assert "CUST-RAVI" in ids and ids["CUST-RAVI"]["home_node_id"] != "DS-07"
    holdout = next((c for c in out if c["role"] == "holdout"), None)
    assert holdout and holdout["customer_id"] not in ("CUST-MEENA", "CUST-RAVI")

    # the picked customer really is holdout: approve, then their chat gets no offer while Meena's does
    client.post("/approve", json={"play_id": "play_chips_ds07_v1"}, headers=_h("v-cust"))
    meena = client.post("/chat", json={"session_id": "CUST-MEENA:web", "text": "Any offers today?"}, headers={**_h("v-cust"), "Accept": "application/json"}).json()[0]
    theirs = client.post("/chat", json={"session_id": f"{holdout['customer_id']}:web", "text": "Any offers today?"}, headers={**_h("v-cust"), "Accept": "application/json"}).json()[0]
    assert "Best before" in meena["text"] or "ಬಳಕೆಗೆ" in meena["text"]
    assert "Best before" not in theirs["text"] and "ಬಳಕೆಗೆ" not in theirs["text"]


def test_chat_stylist_specialist_and_trends(client):
    # CUST-MEENA's home store is DS-07 (the stylist demo anchor); CUST-RAVI's is a different store.
    r = client.post("/chat", json={"session_id": "CUST-MEENA:web", "text": "What goes with a mustard yellow kurta?", "specialist": "stylist"}, headers={**_h("v-stylist"), "Accept": "application/json"})
    assert r.status_code == 200
    env = r.json()[0]
    names = [t["name"] for t in env["tool_calls"]]
    assert "suggest_pairings" in names
    assert len((env.get("list") or {}).get("rows") or []) <= 10

    grocery = client.post("/chat", json={"session_id": "CUST-MEENA:web", "text": "Do you have Cola Zero?"}, headers={**_h("v-stylist"), "Accept": "application/json"}).json()[0]
    grocery_names = [t["name"] for t in grocery["tool_calls"]]
    assert "get_stock" in grocery_names or "find_substitutes" in grocery_names

    client.post("/chat", json={"session_id": "CUST-MEENA:web", "text": "What goes with a mustard yellow kurta?", "specialist": "stylist"}, headers={**_h("v-stylist"), "Accept": "application/json"})
    rec = client.post("/trends/recompute", headers=_h("v-stylist"))
    assert rec.status_code == 200 and rec.json()["rows"] >= 1

    trends = client.get("/trends", params={"node_id": "DS-07"}, headers=_h("v-stylist")).json()
    assert trends and trends[0]["node_id"] == "DS-07" and trends[0]["garment_type"] == "kurta"
    assert trends[0]["data_label"] == "SYNTHETIC"


def test_chat_photo_is_stylist_only(client):
    import base64

    png = open("fixtures/photos/garments/mustard_kurta.png", "rb").read()
    data_url = "data:image/png;base64," + base64.b64encode(png).decode()

    r = client.post("/chat", json={"session_id": "CUST-RAVI:web", "text": "", "specialist": "stylist", "image_data_url": data_url}, headers={**_h("v-photo"), "Accept": "application/json"})
    assert r.status_code == 200
    env = r.json()[0]
    names = [t["name"] for t in env["tool_calls"]]
    assert "describe_garment_photo" in names

    default_specialist = client.post("/chat", json={"session_id": "CUST-RAVI:web", "text": "", "image_data_url": data_url}, headers=_h("v-photo"))
    assert default_specialist.status_code == 422
