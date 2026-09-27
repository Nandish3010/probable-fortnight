"""Offline counterpart to harness/live_sessions_cache.py: what can be measured without Google
Cloud credentials, for the cost estimate and to size what the Firestore cache can save.

    TAAL_MODEL_BACKEND=stub uv run python -m harness.sessions_cache_offline --out eval/raw/<dir>

1. store_reads: wall time of the LocalStore reads the cache replaces (inventory_batches scan per
   stock lookup, customers scan per profile lookup) and one it does not (order_lines), on this
   machine's disk -- the most a Firestore hit can save per lookup.
2. per_turn: the 15-message pool through the real chat code, stub model, one fresh visitor per
   turn, with a fake Firestore client (mirrored from the seeded tenant) and one shared in-memory
   session service standing in for the Agent Engine. Counts Firestore doc reads and hit rate, and
   session-service calls (create/get/append_event) per turn. The stub model's tool choices are
   not Gemini's, so the per-turn counts are indicative, not a production measurement.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from google.adk.sessions import InMemorySessionService

from agents import chat_runtime
from agents.gate import firestore_cache as fc
from agents.gate.config import load_tenant
from agents.gate.firestore_cache import FirestoreCache
from agents.gate.store import LocalStore, OverlayStore
from harness.live_sessions_cache import POOL, TAAL_NOW
from tests.fake_firestore import FakeClient


def _timeit(fn, n: int = 20) -> dict[str, float]:
    xs = []
    for _ in range(n):
        t0 = time.perf_counter()
        fn()
        xs.append((time.perf_counter() - t0) * 1000.0)
    xs.sort()
    return {"p50_ms": round(xs[len(xs) // 2], 2), "max_ms": round(xs[-1], 2), "n": n}


class _CountingSessions(InMemorySessionService):
    def __init__(self) -> None:
        super().__init__()
        self.calls: dict[str, int] = {"create_session": 0, "get_session": 0, "append_event": 0}

    async def create_session(self, **kw: Any):
        self.calls["create_session"] += 1
        return await super().create_session(**kw)

    async def get_session(self, **kw: Any):
        self.calls["get_session"] += 1
        return await super().get_session(**kw)

    async def append_event(self, session, event):
        self.calls["append_event"] += 1
        return await super().append_event(session, event)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--turns", type=int, default=45)
    args = ap.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    os.environ["TAAL_NOW"] = TAAL_NOW
    data_dir = Path(os.environ.get("TAAL_DATA_DIR", ".local/data")).resolve()
    base = LocalStore(data_dir)

    store_reads = {t: _timeit(lambda t=t: base.read(t)) for t in ("inventory_batches", "customers", "order_lines")}

    from agents.customer.chat import reset_sessions, run_chat_async

    client = FakeClient()
    tenant = load_tenant()
    mirror = fc.mirror(data_dir, FirestoreCache(client, tenant.tenant_id))
    orig_build_cache, orig_build_sessions = fc.build_cache, chat_runtime.build_session_service
    sessions = _CountingSessions()
    fc.build_cache = lambda tenant_id=None, project=None: FirestoreCache(client, tenant_id or tenant.tenant_id)
    chat_runtime.build_session_service = lambda *a, **k: sessions
    os.environ["TAAL_SERVING_CACHE"] = "firestore"
    fc.STATS.reset()
    reset_sessions()
    sandbox = Path(args.out / "sandbox")
    turns = []
    try:
        for i in range(args.turns):
            visitor = f"off{uuid.uuid4().hex[:10]}"
            store = OverlayStore(data_dir, sandbox / visitor)
            reads0, calls0 = client.reads, dict(sessions.calls)
            t0 = time.perf_counter()
            env = asyncio.run(run_chat_async(store, "CUST-MEENA:web", POOL[i % len(POOL)], now_iso="2026-09-12T09:05:00Z", visitor_id=visitor))[0]
            turns.append({"i": i, "message": POOL[i % len(POOL)], "ms": round((time.perf_counter() - t0) * 1000, 1), "firestore_reads": client.reads - reads0,
                          "session_calls": {k: sessions.calls[k] - calls0[k] for k in calls0}, "tools": [t["name"] for t in env["tool_calls"] if "args" in t]})
    finally:
        fc.build_cache, chat_runtime.build_session_service = orig_build_cache, orig_build_sessions
        os.environ.pop("TAAL_SERVING_CACHE", None)
        reset_sessions()
        import shutil

        shutil.rmtree(sandbox, ignore_errors=True)

    per_turn_reads = [t["firestore_reads"] for t in turns]
    per_turn_events = [t["session_calls"]["append_event"] for t in turns]
    result = {
        "measured_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "label": "measured locally (this container's disk; stub model; fake Firestore; in-memory session service) -- no Google Cloud call was made",
        "store_reads_ms": store_reads,
        "mirror": {k: mirror[k] for k in ("as_of", "stock_docs", "customer_docs")},
        "per_turn": {
            "turns": len(turns), "firestore_reads_mean": round(statistics.mean(per_turn_reads), 2), "firestore_reads_max": max(per_turn_reads),
            "serving_cache": fc.STATS.snapshot(),
            "session_calls_per_turn_mean": {k: round(statistics.mean(t["session_calls"][k] for t in turns), 2) for k in ("create_session", "get_session", "append_event")},
            "session_events_per_turn_max": max(per_turn_events),
        },
        "turns": turns,
    }
    (args.out / "offline_counts.json").write_text(json.dumps(result, indent=1))
    print(json.dumps({k: v for k, v in result.items() if k != "turns"}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
