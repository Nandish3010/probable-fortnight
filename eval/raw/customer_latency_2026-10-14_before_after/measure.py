"""50 POST /chat calls as Meena, one fresh visitor per call, the 15-message pool cycled: the method of
eval/raw/customer_latency_2026-10-14/measure.py (same prompts, same order, parallelism 1), against a
local server started with serve.py. Adds per-call model/usage/Model Armor accounting from the
server's event log and a spend guard.

    python measure.py <port> <label> <events.jsonl> <max_usd> [n_calls]

Writes <label>_calls.json and <label>_analysis.json here; appends to the spend ledger. Price: $1.65
per 1M input, $9.90 per 1M output tokens (thinking tokens count as output), from usage_metadata.
"""
import json
import statistics
import sys
import time
import urllib.request
from pathlib import Path

PORT, LABEL, EVENTS, MAX_USD = sys.argv[1], sys.argv[2], Path(sys.argv[3]), float(sys.argv[4])
N = int(sys.argv[5]) if len(sys.argv) > 5 else 50
HERE = Path(__file__).parent
API = f"http://127.0.0.1:{PORT}"
EXPECTED_MODEL = "gemini-3.5-flash"
PRICE_IN, PRICE_OUT = 1.65 / 1e6, 9.90 / 1e6
POOL = [
    "hi", "do you have chips?", "any offers for me?", "what tea do you have?", "do you have quinoa?",
    "what's available in snacks?", "I want cola", "any offers?", "STOP", "what do you have",
    "do you have kaju katli?", "is bread in stock?", "hello, what's on offer today", "chips please", "what categories do you sell",
]


def events_for(turn):
    if not EVENTS.exists():
        return []
    return [e for e in map(json.loads, EVENTS.read_text().splitlines()) if e["turn"] == turn]


def cost(evs):
    return sum(e["tok_in"] * PRICE_IN + (e["tok_out"] + e["tok_think"]) * PRICE_OUT for e in evs if e["kind"] == "model")


results, spent, invalid = [], 0.0, []
for i in range(N):
    msg = POOL[i % len(POOL)]
    if spent + 0.05 > MAX_USD:  # a turn costs ~$0.02 to $0.04; stop before it could cross the cap
        print(f"STOP before call {i}: spent ${spent:.4f} of ${MAX_USD}", flush=True)
        break
    visitor = f"latba-{LABEL}-{i:03d}-{int(time.time() * 1000) % 100000}"
    body = json.dumps({"session_id": f"{visitor}:web", "text": msg, "customer_id": "CUST-MEENA"}).encode()
    req = urllib.request.Request(f"{API}/chat", data=body, headers={"Content-Type": "application/json", "X-Taal-Visitor": visitor}, method="POST")
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw, status = resp.read().decode(), resp.status
    except Exception as e:  # noqa: BLE001
        raw, status = str(e), -1
    dt = time.perf_counter() - t0
    time.sleep(0.05)
    evs = events_for(i + 1)
    models = [e for e in evs if e["kind"] == "model"]
    armor = [e for e in evs if e["kind"] == "armor"]
    c = cost(evs)
    spent += c
    wrong = [e["answered"] or e["asked"] for e in models if (e["answered"] or e["asked"]) != EXPECTED_MODEL and not str(e["answered"] or e["asked"]).startswith(EXPECTED_MODEL)]
    if wrong:
        invalid.append({"i": i, "models": wrong})
    guard = None
    try:
        text = raw.split("data: ", 1)[1].split("\n", 1)[0]
        env = json.loads(text)
        guard = env.get("guard")
        tools = [t["name"] for t in env.get("tool_calls", []) if "args" in t]
        reply = env.get("text")
    except Exception:  # noqa: BLE001
        tools, reply = [], raw[:200]
    results.append({"i": i, "message": msg, "latency_s": round(dt, 4), "status": status, "model_calls": len(models), "model_s": round(sum(e["dt"] for e in models), 3), "armor_s": round(sum(e["dt"] for e in armor), 3), "armor_calls": len(armor), "armor_sources": sorted({e["source"] for e in armor}), "tool_calls": tools, "models_seen": sorted({e["answered"] or e["asked"] for e in models}), "thinking": sorted({e["thinking"] for e in models}), "tok_in": sum(e["tok_in"] for e in models), "tok_out": sum(e["tok_out"] + e["tok_think"] for e in models), "usd": round(c, 5), "reply": reply})
    print(f"[{i:2d}] {dt:6.2f}s model_calls={len(models)} armor={sum(e['dt'] for e in armor):.2f}s tools={tools} ${spent:.4f} :: {msg}", flush=True)

(HERE / f"{LABEL}_calls.json").write_text(json.dumps(results, indent=1, ensure_ascii=False), encoding="utf-8")
x = sorted(r["latency_s"] for r in results)
q = statistics.quantiles(x, n=100, method="inclusive") if len(x) > 1 else [x[0]] * 99
analysis = {
    "label": LABEL, "n_calls": len(results), "all_status_200": all(r["status"] == 200 for r in results),
    "valid": not invalid, "invalid_calls": invalid, "expected_model": EXPECTED_MODEL,
    "p50_s": round(statistics.median(x), 3), "p95_s": round(q[94], 3), "max_s": x[-1], "mean_s": round(statistics.mean(x), 3),
    "mean_model_calls_per_turn": round(statistics.mean(r["model_calls"] for r in results), 3),
    "mean_model_s_per_turn": round(statistics.mean(r["model_s"] for r in results), 3),
    "mean_armor_s_per_turn": round(statistics.mean(r["armor_s"] for r in results), 3),
    "armor_sources": sorted({s for r in results for s in r["armor_sources"]}),
    "get_stock_calls": sum(r["tool_calls"].count("get_stock") for r in results),
    "thinking_levels": sorted({t for r in results for t in r["thinking"]}),
    "tokens_in": sum(r["tok_in"] for r in results), "tokens_out_incl_thinking": sum(r["tok_out"] for r in results), "spend_usd": round(spent, 4),
}
(HERE / f"{LABEL}_analysis.json").write_text(json.dumps(analysis, indent=1) + "\n", encoding="utf-8")
print(json.dumps(analysis), flush=True)
