import json
import time
import urllib.request

API = "http://localhost:8080"
POOL = [
    "hi",
    "do you have chips?",
    "any offers for me?",
    "what tea do you have?",
    "do you have quinoa?",
    "what's available in snacks?",
    "I want cola",
    "any offers?",
    "STOP",
    "what do you have",
    "do you have kaju katli?",
    "is bread in stock?",
    "hello, what's on offer today",
    "chips please",
    "what categories do you sell",
]

results = []
for i in range(50):
    msg = POOL[i % len(POOL)]
    visitor = f"latd28-{i:03d}-{int(time.time()*1000) % 100000}"
    body = json.dumps({"session_id": f"{visitor}:web", "text": msg, "customer_id": "CUST-MEENA"}).encode()
    req = urllib.request.Request(f"{API}/chat", data=body, headers={"Content-Type": "application/json", "X-Taal-Visitor": visitor}, method="POST")
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode()
            status = resp.status
    except Exception as e:
        raw = str(e)
        status = -1
    dt = time.perf_counter() - t0
    resp_len = len(raw)
    results.append({"i": i, "message": msg, "visitor": visitor, "latency_s": round(dt, 4), "status": status, "resp_len": resp_len})
    print(f"[{i:2d}] {dt:6.2f}s status={status} :: {msg}")

with open("/home/user/probable-fortnight/eval/raw/customer_latency_2026-09-28/calls.json", "w") as f:
    json.dump(results, f, indent=2)
print("wrote", len(results), "results")
