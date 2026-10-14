"""Daily 5-minute smoke for the judging window. Standard library only; prints PASS or FAIL per check.

    make smoke-judging
    python3 harness/smoke_judging.py [--web URL] [--api URL]

Checks, in order: five web routes return 200; /health fields (status, model, plan_live_eval); one
Approve on Tea with the expected numbers (355 treated, 39 held out, copy.source existing,
provenance bigquery_pregenerated); one chat turn as Ravi (one model call); one Plan live (one model
call, about 27 s). Everything after the web routes uses ONE fresh X-Taal-Visitor sandbox per run, so
the shared base tenant is never written. Exits 1 if any check fails. Run it once a day, not in a loop.
"""
from __future__ import annotations

import argparse
import json
import secrets
import sys
import time
import urllib.error
import urllib.request

WEB = "https://taal-web-2obkp776ca-el.a.run.app"
API = "https://taal-agents-2obkp776ca-el.a.run.app"
ROUTES = ("/", "/desk", "/phone", "/chat", "/outcomes")
TEA_PLAY = "play_tea_ds04_v1"
TEA_GAP = "gap_tea_ds04"
EXPECT = {"treated_n": 355, "holdout_n": 39, "copy.source": "existing", "copy.provenance": "bigquery_pregenerated"}
PLAN_POLL_S = 120
RESULTS: list[tuple[str, bool, str]] = []


def call(method: str, url: str, headers: dict[str, str] | None = None, body: dict | None = None, timeout: float = 60.0) -> tuple[int, str]:
    data = json.dumps(body).encode() if body is not None else None
    h = {"User-Agent": "taal-smoke-judging/1", **(headers or {})}
    if data is not None:
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:  # network error, timeout
        return 0, f"{type(e).__name__}: {e}"


def record(name: str, ok: bool, detail: str) -> bool:
    RESULTS.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}: {detail}", flush=True)
    return ok


def check_routes(web: str) -> None:
    for route in ROUTES:
        t = time.monotonic()
        status, _ = call("GET", web + route, timeout=45)
        record(f"web {route}", status == 200, f"HTTP {status} in {time.monotonic() - t:.2f} s")


def check_health(api: str) -> None:
    status, text = call("GET", api + "/health", timeout=45)
    try:
        body = json.loads(text)
    except ValueError:
        record("api /health", False, f"HTTP {status}, not JSON: {text[:120]}")
        return
    model = body.get("model")
    ple = body.get("plan_live_eval") or {}
    problems = []
    if status != 200 or body.get("status") != "ok":
        problems.append(f"status={body.get('status')!r} HTTP {status}")
    if not model or "2.5" in str(model):
        problems.append(f"model={model!r} (must be set and not the retiring 2.5 line)")
    if not ple.get("total") or ple.get("passed") is None:
        problems.append("plan_live_eval missing")
    detail = f"status={body.get('status')}, model={model}, plan_live_eval={ple.get('passed')}/{ple.get('total')} (p50 {ple.get('p50_s')} s, {ple.get('date')})"
    record("api /health", not problems, detail if not problems else "; ".join(problems) + f" | {detail}")


def check_approve(api: str, visitor: str) -> None:
    t = time.monotonic()
    status, text = call("POST", api + "/approve", {"X-Taal-Visitor": visitor}, {"play_id": TEA_PLAY}, timeout=60)
    took = time.monotonic() - t
    try:
        b = json.loads(text)
        got = {"treated_n": b["assignment"]["treated_n"], "holdout_n": b["assignment"]["holdout_n"],
               "copy.source": b["copy"]["source"], "copy.provenance": b["copy"].get("provenance")}
    except (ValueError, KeyError, TypeError):
        record("approve Tea", False, f"HTTP {status}, unexpected body: {text[:160]}")
        return
    wrong = {k: (got[k], v) for k, v in EXPECT.items() if got[k] != v}
    detail = f"{got['treated_n']} treated / {got['holdout_n']} held out, copy.source {got['copy.source']}, provenance {got['copy.provenance']}, {took:.2f} s"
    record("approve Tea", status == 200 and not wrong, detail if not wrong else f"{detail} | expected {dict((k, v[1]) for k, v in wrong.items())}")


def check_chat(api: str, visitor: str) -> None:
    t = time.monotonic()
    status, text = call("POST", api + "/chat", {"X-Taal-Visitor": visitor, "Accept": "application/json"},
                        {"session_id": "CUST-RAVI:web", "text": "Any offers today?"}, timeout=90)
    took = time.monotonic() - t
    try:
        reply = json.loads(text)[0]["text"]
    except (ValueError, KeyError, IndexError, TypeError):
        record("chat as Ravi", False, f"HTTP {status}, unexpected body: {text[:160]}")
        return
    record("chat as Ravi", status == 200 and bool(str(reply).strip()), f"{took:.1f} s, reply: {str(reply)[:90]!r}")


def check_plan_live(api: str, visitor: str) -> None:
    h = {"X-Taal-Visitor": visitor}
    status, text = call("GET", api + "/policy", h)
    try:
        policy = json.loads(text)["text"]
    except (ValueError, KeyError, TypeError):
        record("plan live", False, f"GET /policy HTTP {status}: {text[:120]}")
        return
    t = time.monotonic()
    status, text = call("POST", api + "/rerun", h, {"gap_id": TEA_GAP, "policy_text": policy}, timeout=60)
    try:
        run_id = json.loads(text)["run_id"]
    except (ValueError, KeyError, TypeError):
        record("plan live", False, f"POST /rerun HTTP {status}: {text[:160]}")
        return
    state: dict = {}
    while time.monotonic() - t < PLAN_POLL_S:
        time.sleep(3)
        status, text = call("GET", f"{api}/rerun/{run_id}", h)
        try:
            state = json.loads(text)
        except ValueError:
            state = {}
        if state.get("status") not in (None, "running"):
            break
    took = time.monotonic() - t
    result = state.get("result") or {}
    source = result.get("planner_source")
    ok = state.get("status") == "done" and source == "model"
    record("plan live", ok, f"status={state.get('status')}, planner_source={source}, {took:.1f} s" + ("" if ok else f", error={result.get('error') or result.get('fallback_reason')}"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--web", default=WEB)
    ap.add_argument("--api", default=API)
    args = ap.parse_args()
    web, api = args.web.rstrip("/"), args.api.rstrip("/")
    visitor = f"smoke-judging-{int(time.time())}-{secrets.token_hex(3)}"
    print(f"smoke-judging: web={web} api={api} visitor={visitor}", flush=True)
    check_routes(web)
    check_health(api)
    check_approve(api, visitor)
    check_chat(api, visitor)
    check_plan_live(api, visitor)
    failed = [n for n, ok, _ in RESULTS if not ok]
    print(f"\n{'FAIL' if failed else 'PASS'}: {len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed" + (f"; failed: {', '.join(failed)}" if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
