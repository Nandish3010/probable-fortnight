"""API contract and judge-mode flows against the FastAPI app with per-visitor sandboxes."""
import asyncio
import json
import os
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agents.planner.stub_llm import StubPlannerLlm


@pytest.fixture
def client(data_dir, tmp_path, monkeypatch):
    monkeypatch.setenv("TAAL_DATA_DIR", str(data_dir))
    monkeypatch.setenv("TAAL_SANDBOX_DIR", str(tmp_path / "sandbox"))
    # The seeded tenant is a snapshot frozen at manifest.json's as_of date (data/generator);
    # play windows and the approve -> re-forecast beat are computed relative to "now", so pin the
    # clock to the snapshot the same way make/Dockerfile do (TAAL_NOW), derived from the tenant
    # actually under test rather than a second hardcoded date that would silently drift out of
    # sync if the tenant is ever regenerated with a different AS_OF.
    as_of = json.loads((data_dir / "manifest.json").read_text())["as_of"]
    monkeypatch.setenv("TAAL_NOW", f"{as_of}T03:30:00Z")
    from agents.customer.chat import reset_sessions
    from services.api.main import app

    reset_sessions()
    return TestClient(app)


def _h(vid):
    return {"X-Taal-Visitor": vid}


def _policy_v2():
    return open(os.path.join(os.path.dirname(__file__), "..", "..", "fixtures", "policy_v2.txt")).read()


def _poll_rerun(client, run_id, headers, timeout_s=30.0, interval_s=0.05):
    """Bounded poll of GET /rerun/{run_id} until it leaves "running" -- never a bare sleep."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        r = client.get(f"/rerun/{run_id}", headers=headers)
        assert r.status_code == 200, r.text
        d = r.json()
        if d["status"] != "running":
            return d
        time.sleep(interval_s)
    raise AssertionError(f"run {run_id} still running for this visitor after {timeout_s}s")


@pytest.fixture
def slow_stub(monkeypatch):
    """Make every planner LLM turn take >=1s (the real StubPlannerLlm.decide still runs, so the
    scripted play logic is untouched) -- long enough to prove POST /rerun answers before the
    planner finishes, without waiting anywhere near as long as a real Gemini call would."""

    async def _slow_generate_content_async(self, llm_request, stream=False):
        await asyncio.sleep(1.0)
        yield self.decide(llm_request)

    monkeypatch.setattr(StubPlannerLlm, "generate_content_async", _slow_generate_content_async)


def _read_sse(resp):
    """Parse an SSE response body into (records, done_payload): every `data:` frame not tagged
    `event: done` goes to `records` in arrival order; the `done` frame's JSON is `done_payload`."""
    records, done_payload, event_name = [], None, None
    for line in resp.iter_lines():
        if not line or line.startswith(":"):
            continue
        if line.startswith("event:"):
            event_name = line.split(":", 1)[1].strip()
            continue
        if line.startswith("data:"):
            payload = json.loads(line[len("data:"):].strip())
            if event_name == "done":
                done_payload = payload
            else:
                records.append(payload)
            event_name = None
    return records, done_payload


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


def test_approve_after_window_end_is_rejected_not_silently_inverted(client, monkeypatch):
    """services/api/approve.py used to rewrite play["window"]["start"] to "now" unconditionally,
    even when "now" is already past the original window end (whenever TAAL_NOW is unset and the
    wall clock has drifted) -- producing an inverted, empty window that touches zero
    future_regressors rows and returns 200 with no write-off movement. Now it fails loudly."""
    monkeypatch.setenv("TAAL_NOW", "2027-01-01T00:00:00Z")  # well past every seeded play window
    r = client.post("/approve", json={"play_id": "play_chips_ds07_v1"}, headers=_h("v-expired"))
    assert r.status_code == 409
    body = r.json()["detail"]
    assert "play window ended" in body and "TAAL_NOW=2027-01-01T00:00:00Z" in body


def test_approve_before_window_end_still_succeeds(client):
    """The other branch of the same guard: approving before the window ends is unaffected."""
    r = client.post("/approve", json={"play_id": "play_chips_ds07_v1"}, headers=_h("v-on-time"))
    assert r.status_code == 200
    assert r.json()["status"] == "approved"


def test_two_visitors_are_isolated_and_reset_is_scoped(client):
    client.post("/approve", json={"play_id": "play_chips_ds07_v1"}, headers=_h("visitor-a"))
    assert client.get("/plays/play_chips_ds07_v1", headers=_h("visitor-a")).json()["status"] == "approved"
    assert client.get("/plays/play_chips_ds07_v1", headers=_h("visitor-b")).json()["status"] == "proposed"
    r = client.post("/reset", headers=_h("visitor-a")).json()
    assert r["ok"] and r["namespace"] == "visitor-a"
    assert client.get("/plays/play_chips_ds07_v1", headers=_h("visitor-a")).json()["status"] == "proposed"
    assert not client.post("/reset").json()["ok"], "no visitor id: base tenant never reset"


def test_headerless_mutating_request_is_rejected_not_written_to_base_tenant(client):
    """A headerless mutating request used to silently write to the shared base tenant -- every
    visitor's judge-mode session reads that state, and the service has no auth. Now rejected.
    /reset is exempt (see services/api/sandbox.py) because it already no-ops safely on its own.
    """
    r = client.post("/approve", json={"play_id": "play_chips_ds07_v1"})
    assert r.status_code == 400
    assert client.get("/plays/play_chips_ds07_v1", headers=_h("v-after-headerless")).json()["status"] != "approved"


def test_chat_sse_and_json(client):
    client.post("/approve", json={"play_id": "play_chips_ds07_v1"}, headers=_h("v-chat"))
    r = client.post("/chat", json={"session_id": "CUST-MEENA:web", "text": "Any offers today?"}, headers=_h("v-chat"))
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    frames = [json.loads(line[5:]) for line in r.text.splitlines() if line.startswith("data:")]
    # play_chips_ds07_v1 is seeded from a real, committed Gemini recording as of 2026-09-28
    # (eval/raw/planner_real_traces_2026-09-28/); the model chose English-only copy for it, so
    # the offer text here is in English, not the Kannada it used to be under the scripted stub.
    # Kannada offer delivery is still covered by fixtures/conversations/01_offer_delivered_kn.json
    # (a scripted-stub play with the tenant's full language set).
    assert frames and "Best before" in frames[0]["text"] and frames[0]["latency_ms"] >= 0
    r2 = client.post("/chat", json={"session_id": "CUST-MEENA:web", "text": "Do you have Cola Zero?"}, headers={**_h("v-chat"), "Accept": "application/json"})
    env = r2.json()[0]
    assert env["list"]["rows"] and len(env["list"]["rows"]) <= 10
    assert client.post("/chat", json={"session_id": "bad session", "text": "x"}, headers=_h("v-chat")).status_code == 422


def test_rerun_with_policy_and_events(client):
    """POST /rerun is asynchronous (202 immediately); poll GET /rerun/{run_id} for the outcome."""
    r = client.post("/rerun", json={"gap_id": "gap_tea_ds04", "policy_text": _policy_v2(), "policy_version": "v2"}, headers=_h("v-rerun"))
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "running" and body["gap_id"] == "gap_tea_ds04" and body["policy_version"] == "v2"
    done = _poll_rerun(client, body["run_id"], _h("v-rerun"))
    assert done["status"] == "done"
    result = done["result"]
    assert result["play"]["policy_version"] == "v2" and result["policy_version"] == "v2"
    ev = client.get(f"/events/{result['run_id']}", headers=_h("v-rerun")).json()
    assert ev["events"] and ev["events"][0]["author"] == "cost_governor" and all("ts_offset_ms" in e for e in ev["events"])
    assert ev["source"] == "scripted_stub"
    # the async worker never appends its own run_summary (agents.planner.run.run_planner_async
    # writes the trace's one terminal record itself) -- exactly one, and the done payload agrees.
    summaries = [e for e in ev["events"] if e.get("kind") == "run_summary"]
    assert len(summaries) == 1
    assert result["source"] == ev["source"] == summaries[0]["source"]
    assert client.get("/policy", headers=_h("v-rerun")).json()["policy_version"] == "v2"
    assert client.get("/events/does-not-exist", headers=_h("v-rerun")).status_code == 404


def test_live_runs_with_unchanged_policy_text_reuse_the_version_but_not_the_recorded_play(client):
    """"Plan live" posts the policy as it stands: that is not a new policy, so it must not write a
    version row. Two consecutive runs under identical text leave one version; different text
    makes exactly one, which the next identical run then reuses. And a run under a reused
    version files its play under its own id (play_<gap>_<version>_live, _live2, ...), so the
    recorded play is never overwritten."""
    h = _h("v-reuse-policy")
    gap, recorded_id = "gap_chips_ds07", "play_chips_ds07_v1"
    recorded = client.get(f"/plays/{recorded_id}", headers=h).json()
    assert recorded["source"] == "recorded_gemini"
    current = client.get("/policy", headers=h).json()
    assert current["updated_at"] is None  # the tenant default: no policy row written yet

    def live(text):
        body = client.post("/rerun", json={"gap_id": gap, "policy_text": text}, headers=h).json()
        done = _poll_rerun(client, body["run_id"], h)
        assert done["status"] == "done"
        return body, done["result"]

    (first, r1), (second, r2) = live(current["text"]), live(current["text"])
    assert first["policy_version"] == second["policy_version"] == current["policy_version"]
    assert first["run_id"] != second["run_id"]
    assert client.get("/policy", headers=h).json() == current  # no row appended

    assert r1["play"]["play_id"] == "play_chips_ds07_v1_live" and r2["play"]["play_id"] == "play_chips_ds07_v1_live2"
    assert client.get(f"/plays/{recorded_id}", headers=h).json() == recorded  # the recorded play is untouched
    for r in (r1, r2):
        live_play = client.get(f"/plays/{r['play']['play_id']}", headers=h).json()
        assert live_play["play_id"] != recorded_id and live_play["source"] != "recorded_gemini"
        assert live_play["trace_ref"] == f"events/{r['run_id']}" != recorded["trace_ref"]
    ids = [p["play_id"] for p in client.get("/plays", headers=h).json() if p["gap_id"] == gap]
    assert ids == [recorded_id, "play_chips_ds07_v1_live", "play_chips_ds07_v1_live2"]
    # the holdout seed is code, derived from the final play id: distinct plays never share one
    plays = {p["play_id"]: p for p in client.get("/plays", headers=h).json() if p["gap_id"] == gap}
    live_ids = ["play_chips_ds07_v1_live", "play_chips_ds07_v1_live2"]
    assert len({plays[i]["holdout"]["seed"] for i in [recorded_id, *live_ids]}) == 3
    # every play that went through propose_play carries seed-<its id>; the recorded play keeps the
    # seed it was recorded with (re-seeding it would change which customers are treated)
    assert all(p["holdout"]["seed"] == f"seed-{pid}" for pid, p in plays.items() if pid != recorded_id)

    (edited, e1), (again, e2) = live(_policy_v2()), live(_policy_v2())
    assert edited["policy_version"] == again["policy_version"] != current["policy_version"]
    assert client.get("/policy", headers=h).json()["policy_version"] == edited["policy_version"]
    assert e1["play"]["play_id"].endswith(f"_{edited['policy_version']}") and e2["play"]["play_id"] == e1["play"]["play_id"] + "_live"
    assert all(p["holdout"]["seed"] == f"seed-{p['play_id']}" for p in (e1["play"], e2["play"]))
    rows = list((Path(os.environ["TAAL_SANDBOX_DIR"]) / "v-reuse-policy").glob("policy.*"))
    assert rows and sum(1 for line in rows[0].read_text().splitlines() if line.strip()) == 1
    assert client.get(f"/plays/{recorded_id}", headers=h).json() == recorded

    # Approve acts on the play it is given: the live one approves without touching the recorded one
    approved = client.post("/approve", json={"play_id": r1["play"]["play_id"]}, headers=h)
    assert approved.status_code == 200 and approved.json()["play_id"] == r1["play"]["play_id"]
    assert client.get(f"/plays/{recorded_id}", headers=h).json() == recorded
    assert client.get(f"/plays/{r1['play']['play_id']}", headers=h).json()["status"] == "approved"


def test_rerun_unknown_gap_is_404_not_202(client):
    r = client.post("/rerun", json={"gap_id": "does-not-exist", "policy_text": _policy_v2(), "policy_version": "v-404"}, headers=_h("v-rerun-404"))
    assert r.status_code == 404


def test_rerun_returns_202_and_is_really_async(client, slow_stub):
    """The POST answers immediately; the planner keeps running on a worker thread afterwards --
    proven by monkeypatching the stub LLM to sleep 1s per turn and finding the run still
    "running" right after the 202 comes back (Starlette's TestClient runs BackgroundTasks to
    completion before returning, so this would fail if /rerun still used those)."""
    t0 = time.monotonic()
    r = client.post("/rerun", json={"gap_id": "gap_tea_ds04", "policy_text": _policy_v2(), "policy_version": "v-async"}, headers=_h("v-async"))
    dt = time.monotonic() - t0
    assert r.status_code == 202
    assert dt < 0.5, f"POST /rerun took {dt:.3f}s; a truly async endpoint should return well under 1s"
    body = r.json()
    assert body["status"] == "running" and body["run_id"] and body["gap_id"] == "gap_tea_ds04"
    assert body["policy_version"] == "v-async" and body["backend"] == "stub"
    assert isinstance(body["deadline_s"], float) and body["deadline_s"] > 0
    assert body["stream_url"] == f"/events/{body['run_id']}/stream"
    assert body["status_url"] == f"/rerun/{body['run_id']}"

    still_running = client.get(body["status_url"], headers=_h("v-async")).json()
    assert still_running["status"] == "running", "the slow stub sleeps 1s per turn; this GET should win the race"

    done = _poll_rerun(client, body["run_id"], _h("v-async"))
    assert done["status"] == "done" and done["result"]["status"] == "proposed"


def test_rerun_stream_contract(client):
    r = client.post("/rerun", json={"gap_id": "gap_tea_ds04", "policy_text": _policy_v2(), "policy_version": "v-stream"}, headers=_h("v-stream"))
    assert r.status_code == 202
    body = r.json()
    with client.stream("GET", body["stream_url"], headers=_h("v-stream")) as resp:
        assert resp.status_code == 200
        records, done_payload = _read_sse(resp)
    assert records, "expected at least one live trace record while the run was in flight"
    assert done_payload is not None, "the stream must end with an `event: done` frame"
    assert done_payload["status"] == "proposed"
    assert done_payload["play"]["gap_id"] == "gap_tea_ds04"
    assert done_payload["policy_version"] == body["policy_version"] == "v-stream"
    # exactly one run_summary record flows through the live SSE trace too -- the worker must not
    # append a second one alongside the planner's own.
    assert sum(1 for r in records if r.get("kind") == "run_summary") == 1
    # the run really did finish by the time the stream closed
    assert client.get(body["status_url"], headers=_h("v-stream")).json()["status"] == "done"


def test_rerun_deadline_exceeded_falls_back_to_deterministic(client, monkeypatch, slow_stub):
    monkeypatch.setenv("TAAL_PLANNER_DEADLINE_S", "0.3")
    r = client.post("/rerun", json={"gap_id": "gap_tea_ds04", "policy_text": _policy_v2(), "policy_version": "v-deadline"}, headers=_h("v-deadline"))
    assert r.status_code == 202
    body = r.json()
    assert body["deadline_s"] == 0.3
    done = _poll_rerun(client, body["run_id"], _h("v-deadline"))
    result = done["result"]
    assert result["planner_source"] == "deterministic_fallback"
    assert result["fallback_reason"].startswith("deadline exceeded")


def test_rerun_isolation_across_visitors_and_no_visitor(client):
    r = client.post("/rerun", json={"gap_id": "gap_tea_ds04", "policy_text": _policy_v2(), "policy_version": "v-iso"}, headers=_h("v-iso-a"))
    assert r.status_code == 202
    run_id = r.json()["run_id"]

    # a different visitor sees none of it
    assert client.get(f"/rerun/{run_id}", headers=_h("v-iso-b")).status_code == 404
    assert client.get(f"/events/{run_id}", headers=_h("v-iso-b")).status_code == 404
    with client.stream("GET", f"/events/{run_id}/stream", headers=_h("v-iso-b")) as resp:
        assert resp.status_code == 404

    # neither does a request with no visitor id at all
    assert client.get(f"/rerun/{run_id}").status_code == 404
    assert client.get(f"/events/{run_id}").status_code == 404
    with client.stream("GET", f"/events/{run_id}/stream") as resp:
        assert resp.status_code == 404

    # the visitor who started it can watch it end to end
    done = _poll_rerun(client, run_id, _h("v-iso-a"))
    assert done["status"] == "done"
    assert client.get(f"/events/{run_id}", headers=_h("v-iso-a")).status_code == 200


def test_rerun_worker_exception_yields_short_error_without_a_traceback(client, monkeypatch):
    import services.api.main as api_main

    async def _boom(*args, **kwargs):
        raise RuntimeError("boom: simulated planner failure")

    monkeypatch.setattr(api_main, "run_planner_async", _boom)
    r = client.post("/rerun", json={"gap_id": "gap_tea_ds04", "policy_text": _policy_v2(), "policy_version": "v-boom"}, headers=_h("v-boom"))
    assert r.status_code == 202
    done = _poll_rerun(client, r.json()["run_id"], _h("v-boom"))
    assert done["status"] == "error"
    result = done["result"]
    assert result["status"] == "error" and "boom" in result["error"]
    assert len(result["error"]) <= 300
    assert "Traceback" not in result["error"] and 'File "' not in result["error"]
    # the visitor is unblocked for a new re-plan after an error, not stuck behind the 409 check
    r2 = client.post("/rerun", json={"gap_id": "gap_tea_ds04", "policy_text": _policy_v2(), "policy_version": "v-after-boom"}, headers=_h("v-boom"))
    assert r2.status_code == 202


def test_rerun_409_on_concurrent_post_same_visitor_other_visitor_unaffected(client, slow_stub):
    r1 = client.post("/rerun", json={"gap_id": "gap_tea_ds04", "policy_text": _policy_v2(), "policy_version": "v-c1"}, headers=_h("v-409"))
    assert r1.status_code == 202
    run_id = r1.json()["run_id"]

    r2 = client.post("/rerun", json={"gap_id": "gap_tea_ds04", "policy_text": _policy_v2(), "policy_version": "v-c2"}, headers=_h("v-409"))
    assert r2.status_code == 409
    assert run_id in r2.json()["detail"]

    r3 = client.post("/rerun", json={"gap_id": "gap_chips_ds07", "policy_text": _policy_v2(), "policy_version": "v-c3"}, headers=_h("v-409-other"))
    assert r3.status_code == 202

    done = _poll_rerun(client, run_id, _h("v-409"))
    assert done["status"] == "done"


def test_rerun_submit_failure_rolls_back_the_registry_claim(client):
    """If claiming the in-flight slot succeeds but starting the run does not (the executor itself
    raises), POST /rerun must fail loudly (5xx) rather than leaving the visitor's slot claimed --
    otherwise every subsequent /rerun for them would 409 ("already running") until the process
    restarts, with no run actually in flight to ever finish and clear it. Restores the executor's
    real `submit` in a `finally` -- deliberately not via the shared `monkeypatch` fixture, whose
    single undo stack this test does not want to disturb (the `client` fixture pushed the env vars
    this test still needs onto that same stack)."""
    import services.api.main as api_main

    original_submit = api_main._REPLAN_EXECUTOR.submit

    def _boom_submit(*args, **kwargs):
        raise RuntimeError("executor unavailable")

    # TestClient re-raises an unhandled server exception by default instead of returning a 500
    # response; a second client with that off is what actually lets us assert the status code.
    from fastapi.testclient import TestClient as _TestClient

    lenient = _TestClient(api_main.app, raise_server_exceptions=False)
    api_main._REPLAN_EXECUTOR.submit = _boom_submit
    try:
        r = lenient.post("/rerun", json={"gap_id": "gap_tea_ds04", "policy_text": _policy_v2(), "policy_version": "v-submit-fail"}, headers=_h("v-submit-fail"))
        assert 500 <= r.status_code < 600
    finally:
        api_main._REPLAN_EXECUTOR.submit = original_submit

    r2 = client.post("/rerun", json={"gap_id": "gap_tea_ds04", "policy_text": _policy_v2(), "policy_version": "v-submit-retry"}, headers=_h("v-submit-fail"))
    assert r2.status_code == 202, "the failed submit must not leave this visitor stuck behind a phantom 409"
    done = _poll_rerun(client, r2.json()["run_id"], _h("v-submit-fail"))
    assert done["status"] == "done"


def test_plan_reports_live_source_and_the_planners_own_plan_source(client):
    """POST /plan's response-level "source" stays "live" (pre-existing contract: this hit the live
    endpoint, not a recorded fixture); the planner's own provenance (agents/planner/run.py's
    PLAN_SOURCES) is surfaced separately as "plan_source" instead of silently overwritten."""
    r = client.post("/plan", json={"gap_id": "gap_tea_ds04"}, headers=_h("v-plan"))
    assert r.status_code == 200
    body = r.json()
    assert body["source"] == "live"
    assert body["plan_source"] == "scripted_stub"


def test_capture_confirm_and_execution(client):
    cap = client.post("/capture", json={"node_id": "DS-07", "photo_ref": "fixtures/photos/pallet_lowconf_test.jpg"}, headers=_h("v-cap")).json()
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


def test_prior_update_is_the_same_for_every_visitor_and_survives_reset(client):
    a = client.get("/outcomes/prior-update", headers=_h("v-prior-a"))
    assert a.status_code == 200
    d = a.json()
    assert d["play_id"] == "play_chips_ds07_v1" and d["data_label"] == "SYNTHETIC"
    client.post("/approve", json={"play_id": "play_chips_ds07_v1"}, headers=_h("v-prior-a"))
    client.post("/measure", headers=_h("v-prior-a"))
    client.post("/reset", headers=_h("v-prior-a"))
    assert client.get("/outcomes/prior-update", headers=_h("v-prior-a")).json() == d
    assert client.get("/outcomes/prior-update", headers=_h("v-prior-b")).json() == d
    assert client.get("/outcomes/prior-update").json() == d


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
