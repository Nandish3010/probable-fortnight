"""50 POST /chat calls as Meena, one fresh visitor per call, the 15-message pool cycled: the method of
eval/raw/customer_latency_2026-09-28/measure.py, pointed at a local API process on gemini-3.5-flash.

    TAAL_MODEL_BACKEND=vertex ... uv run uvicorn services.api.main:app --port 8091 &
    python eval/raw/customer_latency_2026-10-14/measure.py [port]

Writes calls.json and analysis.json next to this file. p95 is the inclusive-interpolation 95th
percentile (statistics.quantiles), the same as the 28 Sep analysis.
"""
import json
import statistics
import sys
import time
import urllib.request
from pathlib import Path

PORT = sys.argv[1] if len(sys.argv) > 1 else "8091"
API = f"http://localhost:{PORT}"
HERE = Path(__file__).parent
POOL = [
    "hi", "do you have chips?", "any offers for me?", "what tea do you have?", "do you have quinoa?",
    "what's available in snacks?", "I want cola", "any offers?", "STOP", "what do you have",
    "do you have kaju katli?", "is bread in stock?", "hello, what's on offer today", "chips please", "what categories do you sell",
]

results = []
for i in range(50):
    msg = POOL[i % len(POOL)]
    visitor = f"latd14-{i:03d}-{int(time.time() * 1000) % 100000}"
    body = json.dumps({"session_id": f"{visitor}:web", "text": msg, "customer_id": "CUST-MEENA"}).encode()
    req = urllib.request.Request(f"{API}/chat", data=body, headers={"Content-Type": "application/json", "X-Taal-Visitor": visitor}, method="POST")
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode()
            status = resp.status
    except Exception as e:  # noqa: BLE001
        raw, status = str(e), -1
    dt = time.perf_counter() - t0
    results.append({"i": i, "message": msg, "visitor": visitor, "latency_s": round(dt, 4), "status": status, "resp_len": len(raw)})
    print(f"[{i:2d}] {dt:6.2f}s status={status} :: {msg}", flush=True)

(HERE / "calls.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
x = sorted(r["latency_s"] for r in results)
per = {}
for m in dict.fromkeys(POOL):
    v = sorted(r["latency_s"] for r in results if r["message"] == m)
    if v:
        per[m] = {"n": len(v), "p50_s": round(statistics.median(v), 3), "max_s": v[-1]}
analysis = {
    "method": "same method as eval/raw/customer_latency_2026-09-28/analysis.json: 50 POST /chat calls as Meena (CUST-MEENA), one fresh visitor per call, 15-message pool cycled, local API process (uv run uvicorn services.api.main:app), TAAL_MODEL_BACKEND=vertex, gemini-3.5-flash",
    "n_calls": len(results),
    "all_status_200": all(r["status"] == 200 for r in results),
    "overall": {
        "p50_s": round(statistics.median(x), 3),
        "p95_s": round(statistics.quantiles(x, n=100, method="inclusive")[94], 3),
        "max_s": x[-1],
        "min_s": x[0],
    },
    "per_message_type": per,
}
(HERE / "analysis.json").write_text(json.dumps(analysis, indent=1) + "\n", encoding="utf-8")
print(json.dumps(analysis["overall"]), "all_200=", analysis["all_status_200"])
