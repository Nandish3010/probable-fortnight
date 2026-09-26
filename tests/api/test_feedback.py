"""POST /feedback and its admin routes, against the local feedback backend in a temp dir.

Every submission here is `source: "test"`: this suite never creates a real-looking response, and
the summary command drops anything that is not `source: "real"` (tests/unit/test_feedback_summary.py).
"""
import json

import pytest
from fastapi.testclient import TestClient

TOKEN = "test-admin-token-not-a-secret"


def _valid(**answers):
    base = {"a1_role": "store_manager", "a2_business": "kirana", "e4_consent": True}
    return {"form_version": "2026-09-26.1", "mode": "self", "source": "test", "answers": {**base, **answers}}


@pytest.fixture
def fb(data_dir, tmp_path, monkeypatch):
    monkeypatch.setenv("TAAL_DATA_DIR", str(data_dir))
    monkeypatch.setenv("TAAL_SANDBOX_DIR", str(tmp_path / "sandbox"))
    monkeypatch.setenv("TAAL_FEEDBACK_STORE", "local")
    monkeypatch.setenv("TAAL_FEEDBACK_DIR", str(tmp_path / "feedback"))
    monkeypatch.setenv("TAAL_FEEDBACK_ADMIN_TOKEN", TOKEN)
    from services.api import main

    main._RATE_LIMITS.clear()
    yield TestClient(main.app), tmp_path / "feedback"
    main._RATE_LIMITS.clear()


def _rows(d, name="feedback_responses"):
    p = d / f"{name}.jsonl"
    return [json.loads(line) for line in p.read_text().splitlines()] if p.exists() else []


def test_valid_submission_is_stored_with_server_fields(fb):
    client, d = fb
    r = client.post("/feedback", json=_valid(c0_seen_demo="yes_live", c1_usefulness=4, c2_most_valuable=["human_approval", "holdout_measurement"], d1_biggest_pain="Curd expires before the weekend."))
    assert r.status_code == 200, r.text
    rid = r.json()["response_id"]
    [row] = _rows(d)
    assert row["response_id"] == rid and len(rid) == 32
    assert row["source"] == "test" and row["mode"] == "self" and row["has_contact"] is False
    assert row["submitted_at"].endswith("Z") and not row["submitted_at"].startswith("2026-09-12"), "real clock, not the demo's TAAL_NOW pin"
    assert row["answers"]["c1_usefulness"] == 4


def test_contact_is_split_off_from_answers(fb):
    client, d = fb
    r = client.post("/feedback", json=_valid(e1_pilot="yes", e3_contact={"name": "Test Person", "reach": "test@example.invalid"}))
    assert r.status_code == 200, r.text
    [row] = _rows(d)
    assert "e3_contact" not in row["answers"] and row["has_contact"] is True
    assert "test@example.invalid" not in json.dumps(row)
    [contact] = _rows(d, "feedback_contacts")
    assert contact["response_id"] == row["response_id"] and contact["reach"] == "test@example.invalid"


def test_missing_consent_is_a_422_and_nothing_is_stored(fb):
    client, d = fb
    doc = _valid()
    del doc["answers"]["e4_consent"]
    assert client.post("/feedback", json=doc).status_code == 422
    doc["answers"]["e4_consent"] = False
    assert client.post("/feedback", json=doc).status_code == 422
    assert _rows(d) == []


@pytest.mark.parametrize("answers", [
    {"c0_seen_demo": "no", "c1_usefulness": 5},                   # skipped section must be absent
    {"c4_pay_model": "one_time", "c5_pay_amount": "under_1k", "c0_seen_demo": "yes_live"},  # c5 only after monthly_per_store
    {"e1_pilot": "no", "e3_contact": {"name": "x"}},             # contact only for yes/maybe
    {"c0_seen_demo": "yes_live", "c2_most_valuable": ["cost", "trust_ai"]},  # not options of c2
    {"c0_seen_demo": "yes_live", "c2_most_valuable": ["sellby_deadline", "targeted_offers", "human_approval"]},  # max two
    {"a1_role_other": "buyer"},                                   # other-text without "other"
    {"d1_biggest_pain": "x" * 1001},                              # server-side length cap
    {"unknown_question": "yes"},
])
def test_invalid_answers_are_rejected(fb, answers):
    client, d = fb
    assert client.post("/feedback", json=_valid(**answers)).status_code == 422
    assert _rows(d) == []


def test_conditional_fields_accepted_when_shown(fb):
    client, _ = fb
    ok = _valid(a1_role="other", a1_role_other="Buyer", c0_seen_demo="yes_video", c3_blockers=["other"], c3_blockers_other="Franchise rules", c4_pay_model="monthly_per_store", c5_pay_amount="1k_5k", e1_pilot="maybe")
    assert client.post("/feedback", json=ok).status_code == 200


def test_honeypot_discards_silently(fb):
    client, d = fb
    r = client.post("/feedback", json={**_valid(), "website": "http://spam.example"})
    assert r.status_code == 200 and r.json()["ok"] is True and len(r.json()["response_id"]) == 32
    # Even an otherwise-invalid bot payload gets the same answer, and nothing is written.
    r2 = client.post("/feedback", json={"website": "x", "answers": {}})
    assert r2.status_code == 200
    assert _rows(d) == []


def test_oversized_body_is_rejected(fb):
    client, d = fb
    doc = _valid(d1_biggest_pain="ok")
    doc["padding"] = "x" * 20_000
    r = client.post("/feedback", content=json.dumps(doc), headers={"Content-Type": "application/json"})
    assert r.status_code == 413
    assert _rows(d) == []


def test_rate_limit(fb):
    client, _ = fb
    h = {"X-Taal-Visitor": "rate-limit-probe"}
    codes = [client.post("/feedback", json=_valid(), headers=h).status_code for _ in range(21)]
    assert codes[:20] == [200] * 20 and codes[20] == 429


def test_global_rate_limit_is_not_dodged_by_rotating_visitor_ids(fb):
    client, _ = fb
    from services.api import main

    main._RATE_LIMITS["feedback:all"] = [__import__("time").time()] * 300
    r = client.post("/feedback", json=_valid(), headers={"X-Taal-Visitor": "fresh-visitor-id"})
    assert r.status_code == 429


def test_feedback_needs_no_visitor_header_but_base_tenant_stays_protected(fb):
    client, _ = fb
    assert client.post("/feedback", json=_valid()).status_code == 200
    from services.api.sandbox import _EXEMPT_PATHS

    assert "/feedback" in _EXEMPT_PATHS
    # The guard still blocks every other headerless write to the shared base tenant.
    assert client.post("/approve", json={"play_id": "play_chips_ds07_v1"}).status_code == 400
    assert client.put("/policy", json={"text": "x", "policy_version": "vX"}).status_code == 400
    assert client.post("/execution", json={"play_id": "p", "node_id": "DS-07", "steps_done": []}).status_code == 400


def test_reset_demo_data_cannot_delete_responses(fb):
    client, d = fb
    client.post("/feedback", json=_valid(), headers={"X-Taal-Visitor": "visitor-reset"})
    assert client.post("/reset", headers={"X-Taal-Visitor": "visitor-reset"}).json()["ok"]
    assert client.post("/reset").json()["ok"] is False
    assert len(_rows(d)) == 1


def test_form_is_served_from_config(fb):
    client, _ = fb
    form = client.get("/feedback/form").json()
    assert form["form_version"] == json.load(open("config/feedback_form.json"))["form_version"]


def test_summary_and_delete_require_the_admin_token(fb, monkeypatch):
    client, d = fb
    assert client.get("/feedback/summary").status_code == 401
    assert client.get("/feedback/summary", headers={"Authorization": "Bearer wrong"}).status_code == 401
    rid = client.post("/feedback", json=_valid(e1_pilot="yes", e3_contact={"reach": "test@example.invalid"})).json()["response_id"]
    assert client.delete(f"/feedback/{rid}").status_code == 401
    auth = {"Authorization": f"Bearer {TOKEN}"}
    s = client.get("/feedback/summary", headers=auth).json()
    assert s["responses"]["total"] == 0 and s["excluded_non_real"] == 1, "test rows never counted"
    assert "test@example.invalid" not in json.dumps(s)
    assert client.delete(f"/feedback/{rid}", headers=auth).json()["deleted"] is True
    assert _rows(d) == [] and _rows(d, "feedback_contacts") == []
    assert client.delete(f"/feedback/{rid}", headers=auth).status_code == 404
    monkeypatch.delenv("TAAL_FEEDBACK_ADMIN_TOKEN")
    assert client.get("/feedback/summary", headers=auth).status_code == 503, "never open when unconfigured"
