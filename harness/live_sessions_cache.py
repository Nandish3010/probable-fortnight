"""Live acceptance runs for Vertex AI Sessions + the Firestore serving cache on /chat.

    GOOGLE_APPLICATION_CREDENTIALS=... TAAL_MODEL_BACKEND=vertex GOOGLE_CLOUD_PROJECT=amru-509214 \\
      uv run python -m harness.live_sessions_cache restart --sessions --out eval/raw/<dir>
    ... latency --sessions [--cache] --n 50 --out eval/raw/<dir>

Each mode starts its OWN local API process (uvicorn services.api.main:app) with the flags under
test and TAAL_NOW pinned, so "restart" really kills and relaunches the process. The numbers are
"local API process to real Vertex/Firestore": `*.a.run.app` is not reachable from the build
sandbox, the same method as eval/raw/customer_latency_fix_2026-09-21.json.

- restart: visitors A and B both chat as CUST-MEENA; the API process is killed and restarted;
  both continue. Then the Agent Engine sessions are read back directly: A's holds A's turns from
  both processes and none of B's, and vice versa.
- latency: N sequential /chat calls, one fresh X-Taal-Visitor per call, cycling the same
  15-message pool as the 2026-09-21 run. Per-call latency, the per-turn split of session-service
  I/O vs the rest (TAAL_CHAT_TIMING_LOG), and the serving-cache read/hit counters from /health.

Not part of `make verify`: it needs a project, and in vertex mode each call bills Gemini tokens.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import signal
import socket
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POOL = ["hi", "do you have chips?", "any offers for me?", "what tea do you have?", "do you have quinoa?", "what's available in snacks?", "I want cola", "any offers?", "STOP", "what do you have", "do you have kaju katli?", "is bread in stock?", "hello, what's on offer today", "chips please", "what categories do you sell"]
CUSTOMER = "CUST-MEENA"
TAAL_NOW = "2026-09-12T03:30:00Z"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Api:
    def __init__(self, env: dict[str, str], log: Path):
        self.env, self.log, self.port, self.proc = env, log, _free_port(), None

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def start(self) -> None:
        self.proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "services.api.main:app", "--port", str(self.port)], cwd=ROOT, env=self.env, stdout=open(self.log, "a"), stderr=subprocess.STDOUT)
        for _ in range(120):
            try:
                urllib.request.urlopen(self.url + "/health", timeout=5)
                return
            except Exception:
                time.sleep(0.5)
        raise RuntimeError(f"API never came up; see {self.log}")

    def kill(self) -> None:
        if self.proc:
            self.proc.send_signal(signal.SIGKILL)
            self.proc.wait()
            self.proc = None


def _post(url: str, path: str, body: dict, visitor: str, timeout: float = 120) -> tuple[int, dict | str, float]:
    req = urllib.request.Request(url + path, data=json.dumps(body).encode(), method="POST", headers={"X-Taal-Visitor": visitor, "Content-Type": "application/json", "Accept": "application/json"})
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read()), time.perf_counter() - t0
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace")[:300], time.perf_counter() - t0


def _get(url: str, path: str) -> dict:
    with urllib.request.urlopen(url + path, timeout=30) as r:
        return json.loads(r.read())


def _env(args: argparse.Namespace, timing_log: Path) -> dict[str, str]:
    env = dict(os.environ)
    env.update({"TAAL_NOW": TAAL_NOW, "TAAL_TENANT_CONFIG": "config/tenant.demo.toml", "TAAL_CHAT_TIMING_LOG": str(timing_log), "TAAL_SANDBOX_DIR": str(args.out / "sandbox")})
    for k in ("TAAL_SESSION_BACKEND", "TAAL_SERVING_CACHE"):
        env.pop(k, None)
    if args.sessions:
        env["TAAL_SESSION_BACKEND"] = "vertex"
        env.setdefault("TAAL_AGENT_ENGINE_ID", "5616208637656563712")
    if args.cache:
        env["TAAL_SERVING_CACHE"] = "firestore"
    return env


def _pct(xs: list[float], q: float) -> float:
    s = sorted(xs)
    return round(s[min(len(s) - 1, int(q * len(s)))], 4)


def latency(args: argparse.Namespace) -> dict:
    timing_log = args.out / "chat_timing.jsonl"
    api = Api(_env(args, timing_log), args.out / "api.log")
    api.start()
    rows = []
    try:
        for i in range(args.n):
            visitor = f"lat{uuid.uuid4().hex[:12]}"
            msg = POOL[i % len(POOL)]
            st, body, dt = _post(api.url, "/chat", {"session_id": f"{CUSTOMER}:web", "text": msg}, visitor)
            rows.append({"i": i, "message": msg, "visitor": visitor, "latency_s": round(dt, 4), "status": st, "resp_len": len(json.dumps(body))})
            print(f"{i:2d} {st} {dt:6.2f}s {msg}", flush=True)
        health = _get(api.url, "/health")
    finally:
        api.kill()
    ok = [r["latency_s"] for r in rows if r["status"] == 200]
    timing = [json.loads(line) for line in timing_log.read_text().splitlines()] if timing_log.exists() else []
    summary = {
        "measured_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "method": ("local API process to real Vertex/Firestore (the deployed *.a.run.app is not reachable from this sandbox)" if os.environ.get("TAAL_MODEL_BACKEND") == "vertex" else "SYNTHETIC mechanics check: local API process, stub model, no Gemini call -- not a latency result") + "; sequential calls, one fresh X-Taal-Visitor per call, 15-message pool cycled",
        "note": "session_io_ms counts calls through the Vertex session wrapper only (0 with in-memory sessions)",
        "flags": {"TAAL_SESSION_BACKEND": "vertex" if args.sessions else "unset", "TAAL_SERVING_CACHE": "firestore" if args.cache else "unset", "TAAL_MODEL_BACKEND": os.environ.get("TAAL_MODEL_BACKEND", "stub"), "TAAL_NOW": TAAL_NOW},
        "n_total": len(rows), "n_ok": len(ok), "n_error": len(rows) - len(ok),
        "p50": _pct(ok, 0.5) if ok else None, "p95": _pct(ok, 0.95) if ok else None, "min": min(ok) if ok else None, "max": max(ok) if ok else None, "mean": round(statistics.mean(ok), 4) if ok else None,
        "acceptance_p95_lt_6s": bool(ok) and _pct(ok, 0.95) < 6.0,
        "session_io_ms": {"p50": _pct([t["session_io_ms"] for t in timing], 0.5), "p95": _pct([t["session_io_ms"] for t in timing], 0.95), "calls_per_turn_mean": round(statistics.mean(t["session_calls"] for t in timing), 2)} if timing else None,
        "server_turn_ms": {"p50": _pct([t["latency_ms"] for t in timing], 0.5), "p95": _pct([t["latency_ms"] for t in timing], 0.95)} if timing else None,
        "serving_cache": health["checks"]["firestore"].get("reads"), "health_checks": {k: health["checks"][k] for k in ("sessions", "firestore")},
    }
    (args.out / "latency_calls.json").write_text(json.dumps(rows, indent=1))
    (args.out / "latency_summary.json").write_text(json.dumps(summary, indent=1))
    return summary


def _session_texts(visitor: str) -> list[str]:
    from agents.chat_runtime import adk_ids
    from agents.customer.chat import APP
    from agents.vertex_sessions import build_session_service

    user_id, session_id = adk_ids(visitor, CUSTOMER, f"{CUSTOMER}:web")
    session = asyncio.run(build_session_service().get_session(app_name=APP, user_id=user_id, session_id=session_id))
    if session is None:
        return []
    return [p.text for ev in session.events if ev.author == "user" and ev.content for p in (ev.content.parts or []) if p.text]


def restart(args: argparse.Namespace) -> dict:
    if not args.sessions:
        raise SystemExit("restart needs --sessions: an in-memory session cannot survive a restart by design")
    env = _env(args, args.out / "chat_timing.jsonl")
    api = Api(env, args.out / "api.log")
    stamp = uuid.uuid4().hex[:8]
    a, b = f"restart-a-{stamp}", f"restart-b-{stamp}"
    steps = []

    def turn(visitor: str, text: str, process: int) -> None:
        st, body, dt = _post(api.url, "/chat", {"session_id": f"{CUSTOMER}:web", "text": text}, visitor)
        steps.append({"process": process, "visitor": visitor, "text": text, "status": st, "latency_s": round(dt, 3), "reply": body[0]["text"] if st == 200 else body})

    api.start()
    pid1 = api.proc.pid
    turn(a, "do you have chips?", 1)
    turn(b, "is bread in stock?", 1)
    api.kill()
    api.start()
    pid2 = api.proc.pid
    turn(a, "what did I just ask you about?", 2)
    turn(b, "what did I just ask you about?", 2)
    api.kill()
    os.environ.update({k: v for k, v in env.items() if k.startswith("TAAL_") or k.startswith("GOOGLE_")})
    hist_a, hist_b = _session_texts(a), _session_texts(b)
    result = {
        "measured_at": datetime.now(UTC).isoformat(timespec="seconds"), "method": "two local API processes in sequence (first SIGKILLed), real Agent Engine, real Gemini",
        "process_pids": [pid1, pid2], "steps": steps, "agent_engine_history": {"a": hist_a, "b": hist_b},
        "checks": {
            "a_kept_turns_across_restart": any("chips" in t for t in hist_a) and any("just ask" in t for t in hist_a),
            "b_kept_turns_across_restart": any("bread" in t for t in hist_b) and any("just ask" in t for t in hist_b),
            "a_never_sees_b": not any("bread" in t for t in hist_a),
            "b_never_sees_a": not any("chips" in t for t in hist_b),
        },
    }
    result["pass"] = all(result["checks"].values())
    (args.out / "restart.json").write_text(json.dumps(result, indent=1, ensure_ascii=False))
    return result


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["restart", "latency"])
    ap.add_argument("--sessions", action="store_true", help="TAAL_SESSION_BACKEND=vertex")
    ap.add_argument("--cache", action="store_true", help="TAAL_SERVING_CACHE=firestore")
    ap.add_argument("--n", type=int, default=50)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    out = restart(args) if args.mode == "restart" else latency(args)
    print(json.dumps({k: v for k, v in out.items() if k not in ("steps", "health_checks")}, indent=1, ensure_ascii=False))
    return 0 if out.get("pass", out.get("acceptance_p95_lt_6s", True)) else 1


if __name__ == "__main__":
    raise SystemExit(main())
