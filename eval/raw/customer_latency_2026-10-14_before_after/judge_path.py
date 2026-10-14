"""AFTER-only judge-path check (the remaining budget allowed no BEFORE twin): Approve Tea, then as Ravi
a stock question about the offered Darjeeling Tea, then the Add to cart click. Prints replies, tools, model calls, spend."""
import json
import sys
import time
import urllib.request

PORT, EVENTS, CAP = sys.argv[1], sys.argv[2], float(sys.argv[3])
V = f"latba-judge-{int(time.time())}"
H = {"Content-Type": "application/json", "X-Taal-Visitor": V, "Accept": "application/json"}
def post(path, body):
    t = time.perf_counter()
    r = urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:{PORT}{path}", json.dumps(body).encode(), H, method="POST"), timeout=60)
    return json.loads(r.read()), time.perf_counter() - t
def spend(turn):
    ev = [json.loads(line) for line in open(EVENTS)]
    m = [e for e in ev if e["turn"] == turn and e["kind"] == "model"]
    return len(m), sum(e["tok_in"] * 1.65e-6 + (e["tok_out"] + e["tok_think"]) * 9.9e-6 for e in m), sorted({e["answered"] for e in m})
out, total = [], 0.0
approve, dt = post("/approve", {"play_id": "play_tea_ds04_v1"})
print("approve", round(dt, 2), approve.get("assignment"))
turn = int(sys.argv[4])
for text in ("Is Darjeeling Tea in stock?", "add:SKU-DARJEELING-TEA-100G"):
    if total + 0.045 > CAP:
        print("stop: cap")
        break
    turn += 1
    env, dt = post("/chat", {"session_id": "CUST-RAVI:web", "text": text, "customer_id": "CUST-RAVI"})
    n, usd, models = spend(turn)
    total += usd
    e = env[0]
    out.append({"text_in": text, "latency_s": round(dt, 2), "model_calls": n, "models": models, "usd": round(usd, 4), "tools": [t["name"] for t in e["tool_calls"] if "args" in t], "reply": e["text"], "citations": e.get("citations"), "buttons": e.get("buttons")})
    print(json.dumps(out[-1], ensure_ascii=False))
json.dump({"visitor": V, "turns": out, "usd": round(total, 4)}, open("judge_path_after.json", "w"), indent=1, ensure_ascii=False)
