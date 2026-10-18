"""v4 live checks against a LOCAL API on the v4 code with the real model (TAAL_MODEL_BACKEND=vertex): Plan live on the demo Tea and
Quinoa gaps, 3 runs each, then Approve on the recorded Tea play. Reports results unchanged.

    python -m eval.sealed.v4.live_checks --api http://localhost:8081 --out eval/raw/sealed_v4_live_2026-10-19.json
"""
from __future__ import annotations

import argparse
import json
import time
import urllib.request
from pathlib import Path


def call(method: str, url: str, headers: dict | None = None, body: dict | None = None, timeout: int = 120):
    req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body is not None else None, headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode() or "null")
    except urllib.error.HTTPError as e:
        return e.code, {"error": e.read().decode()[:300]}


def plan_live(api: str, visitor: str, gap_id: str) -> dict:
    h = {"X-Taal-Visitor": visitor}
    _, policy = call("GET", api + "/policy", h)
    t = time.monotonic()
    status, acc = call("POST", api + "/rerun", h, {"gap_id": gap_id, "policy_text": policy["text"]})
    if status != 202:
        return {"gap_id": gap_id, "accepted": False, "http": status, "body": acc}
    state = {}
    while time.monotonic() - t < 150:
        time.sleep(1.5)
        _, state = call("GET", f"{api}/rerun/{acc['run_id']}", h)
        if state.get("status") not in (None, "running"):
            break
    took = time.monotonic() - t
    res = state.get("result") or {}
    _, ev = call("GET", f"{api}/events/{acc['run_id']}", h)
    events = ev if isinstance(ev, list) else (ev or {}).get("events", [])
    summary = next((e for e in reversed(events) if e.get("kind") == "run_summary"), {})
    calls = [e["function_call"]["name"] for e in events if e.get("function_call")]
    play = res.get("play") or {}
    return {"gap_id": gap_id, "status": state.get("status"), "planner_source": res.get("planner_source"), "source": res.get("source"), "latency_s": round(took, 1), "elapsed_ms": summary.get("elapsed_ms"),
            "tool_calls": calls, "model_turns": (summary.get("usage") or {}).get("total_token_count") and None, "mechanic": play.get("mechanic"), "play_id": play.get("play_id"),
            "margin_inr": (play.get("expected_outcome") or {}).get("margin_inr"), "fallback_reason": res.get("fallback_reason"), "usage": summary.get("usage")}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://localhost:8081")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    out: dict = {"api": a.api, "plan_live": []}
    for gap in ("gap_tea_ds04", "gap_quinoa_out02"):
        for i in range(3):
            r = plan_live(a.api, f"v4-live-{gap}-{i}-{int(time.time())}", gap)
            print(r, flush=True)
            out["plan_live"].append(r)
    v = f"v4-approve-{int(time.time())}"
    _, play = call("GET", a.api + "/plays/play_tea_ds04_v1", {"X-Taal-Visitor": v})
    status, ap_body = call("POST", a.api + "/approve", {"X-Taal-Visitor": v}, {"play_id": "play_tea_ds04_v1"})
    p = (play or {}).get("play") or play or {}
    out["approve_tea"] = {"http": status, "treated_n": (ap_body.get("assignment") or {}).get("treated_n"), "holdout_n": (ap_body.get("assignment") or {}).get("holdout_n"), "copy": ap_body.get("copy"),
                          "expected_outcome": p.get("expected_outcome"), "counterfactuals": p.get("counterfactuals"), "mechanic": p.get("mechanic")}
    print(out["approve_tea"], flush=True)
    Path(a.out).write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
