"""Exercise every API endpoint against a running Taal API and print one line per call.

    uv run python -m harness.sweep_live http://localhost:8080
    uv run python -m harness.sweep_live https://taal-agents-<hash>-el.a.run.app

Runs inside its own judge-mode sandbox (X-Taal-Visitor: sweep-1), so it never touches the base
tenant. With TAAL_MODEL_BACKEND=vertex on the target, /plan, /rerun, /chat and an uploaded
/capture make real Gemini calls (each 5-110 s); the three sample pallets replay their recorded
reads. Not part of `make verify` -- it needs a live server and, for the vertex paths, a project.
"""
import json
import sys
import time
import urllib.error
import urllib.request

API = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8080"
VID = "sweep-1"
H = {"X-Taal-Visitor": VID, "Content-Type": "application/json", "Accept": "application/json"}

def call(method, path, data=None, timeout=240, stream=False):
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(API + path, data=body, method=method, headers=H)
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read(4000) if stream else r.read()
            try:
                parsed = json.loads(raw)
            except Exception:
                parsed = raw.decode(errors="replace")
            return r.status, parsed, time.time() - t0
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace")[:300], time.time() - t0
    except Exception as e:
        return "ERR", str(e)[:200], time.time() - t0

def show(label, res, pick=None):
    st, body, dt = res
    summ = pick(body) if (pick and st == 200) else (json.dumps(body)[:160] if not isinstance(body, str) else body[:160])
    flag = "OK " if st == 200 else ("4xx" if isinstance(st, int) and 400 <= st < 500 else "FAIL")
    print(f"{flag} {st!s:4} {dt:6.1f}s  {label:38} {summ}")

png = "data:image/png;base64," + "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="

show("POST /reset", call("POST", "/reset", {}))
show("GET /health", call("GET", "/health"), lambda b: f"{b['status']} backend={b.get('backend')} " + " ".join(f"{k}={'ok' if v['ok'] else 'FAIL'}" for k,v in b['checks'].items()))
st, gaps, _ = r = call("GET", "/gaps")
show("GET /gaps", r, lambda b: f"{len(b)} gaps")
gap_id = next((g["gap_id"] for g in gaps if g["gap_id"] == "gap_chips_ds07"), gaps[0]["gap_id"]) if st == 200 and gaps else "gap_chips_ds07"
show(f"GET /gaps/{gap_id}", call("GET", f"/gaps/{gap_id}"), lambda b: f"{b['type']} {b['sku']} ₹{b['rupees_at_stake']}")
st, plays, _ = r = call("GET", "/plays")
show("GET /plays", r, lambda b: f"{len(b)} plays")
play_id = "play_chips_ds07_v1"
show(f"GET /plays/{play_id}", call("GET", f"/plays/{play_id}"), lambda b: f"{b['mechanic']} status={b['status']}")
show("GET /sense/last", call("GET", "/sense/last"), lambda b: f"run={b.get('run_id')}")
show("GET /policy", call("GET", "/policy"), lambda b: f"{b.get('policy_version')} {len(b.get('text',''))} chars")
st, demo, _ = r = call("GET", f"/customers/demo?play_id={play_id}")
show("GET /customers/demo", r, lambda b: ", ".join(f"{c['customer_id']}({c['role']})" for c in b))
holdout_id = next((c["customer_id"] for c in (demo if isinstance(demo, list) else []) if c.get("role") == "holdout"), "CUST-00316")
show("GET /outcomes (before)", call("GET", "/outcomes"), lambda b: f"{len(b)} rows")
st, planned, _ = r = call("POST", "/plan", {"gap_id": gap_id}, timeout=300)
show("POST /plan (LIVE Gemini planner)", r, lambda b: f"status={b.get('status')} iterations={b.get('iterations')} play={(b.get('play') or {}).get('play_id')} mechanic={(b.get('play') or {}).get('mechanic')} run={b.get('run_id')}")
plan_run_id = planned.get("run_id") if isinstance(planned, dict) else None
# the live plan replaces the seeded play (new holdout seed): re-read who the holdout customer is now
st, demo, _ = call("GET", f"/customers/demo?play_id={play_id}")
holdout_id = next((c["customer_id"] for c in (demo if isinstance(demo, list) else []) if c.get("role") == "holdout"), holdout_id)
st, appr, _ = r = call("POST", "/approve", {"play_id": play_id}, timeout=120)
show("POST /approve", r, lambda b: f"status={b.get('status')} source={b.get('source')} holdout_n={b['assignment'].get('holdout_n')} writeoff {b['forecast'].get('writeoff_before_inr')}->{b['forecast'].get('writeoff_after_inr')}")
show("POST /approve (again, idempotent)", call("POST", "/approve", {"play_id": play_id}, timeout=120), lambda b: f"note={b.get('note')!r} elapsed={b.get('elapsed_ms')}ms")
run_id = plan_run_id
show(f"GET /events/{run_id}", call("GET", f"/events/{run_id}"), lambda b: f"{len(b)} events")
show(f"GET /events/{run_id}/stream", call("GET", f"/events/{run_id}/stream", stream=True), lambda b: f"{str(b)[:60]!r}")
show("POST /chat offers? (LIVE Gemini)", call("POST", "/chat", {"session_id": "CUST-MEENA:web", "text": "Any offers today?", "customer_id": "CUST-MEENA"}, timeout=120), lambda b: (b[-1]['text'][:110] if isinstance(b, list) and b else str(b)[:110]))
show("POST /chat Cola Zero? (LIVE Gemini)", call("POST", "/chat", {"session_id": "CUST-MEENA:web", "text": "Do you have Cola Zero?", "customer_id": "CUST-MEENA"}, timeout=120), lambda b: (b[-1]['text'][:110] if isinstance(b, list) and b else str(b)[:110]))
show(f"POST /chat holdout {holdout_id}", call("POST", "/chat", {"session_id": f"{holdout_id}:web", "text": "Any offers today?", "customer_id": holdout_id}, timeout=120), lambda b: (b[-1]['text'][:110] if isinstance(b, list) and b else str(b)[:110]))
st, pol, _ = r = call("GET", "/policy")
policy_text = pol.get("text", "") if isinstance(pol, dict) else ""
show("POST /rerun (policy re-plan, LIVE)", call("POST", "/rerun", {"gap_id": "gap_tea_ds04", "policy_text": policy_text + "\n8. Premium tea is never discounted; move it to outlets instead.", "policy_version": "v2-sweep"}, timeout=300), lambda b: f"status={b.get('status')} iterations={b.get('iterations')} mechanic={(b.get('play') or {}).get('mechanic')} policy={b.get('policy_version')}")
show("PUT /policy", call("PUT", "/policy", {"policy_version": "v3-sweep", "text": policy_text}), lambda b: f"{b.get('policy_version')}")
show("POST /capture (sample -> recorded)", call("POST", "/capture", {"node_id": "DS-07", "photo_ref": "fixtures/photos/pallet_01.jpg"}, timeout=120), lambda b: f"model={b.get('model_id')} rows={len(b['rows'])}")
st, cap, _ = r = call("POST", "/capture", {"node_id": "DS-07", "image_data_url": png}, timeout=120)
show("POST /capture (upload -> LIVE Gemini)", r, lambda b: f"model={b.get('model_id')} rows={len(b['rows'])}")
rows = [dict(r_, confirmed=True) for r_ in (cap.get("rows", []) if isinstance(cap, dict) else [])] or [{"sku_guess":"SKU-MASALA-CHIPS-200G","sku_confidence":0.9,"best_before_date":"2026-11-15","date_confidence":0.9,"facings_count":8,"count_confidence":0.9,"needs_confirmation":False}]
show("POST /capture/confirm", call("POST", "/capture/confirm", {"node_id": "DS-07", "photo_ref": "upload", "rows": rows}), lambda b: f"{json.dumps(b)[:120]}")
show("POST /execution", call("POST", "/execution", {"play_id": play_id, "node_id": "DS-07", "steps_done": ["print", "place"]}), lambda b: f"{json.dumps(b)[:120]}")
show("POST /measure", call("POST", "/measure", {}, timeout=120), lambda b: f"{json.dumps(b)[:140]}")
show("GET /outcomes (after)", call("GET", "/outcomes"), lambda b: f"{len(b)} rows; " + "; ".join(f"{o.get('play_id')}:{o.get('status')}" for o in b[:3]))
show("GET /gaps unknown id (expect 404)", call("GET", "/gaps/nope"))
show("POST /chat bad session id (expect 422)", call("POST", "/chat", {"session_id": "bad", "text": "hi"}))
show("POST /approve unknown play (expect 404)", call("POST", "/approve", {"play_id": "nope"}))
