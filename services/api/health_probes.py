"""/health's "sessions" and "firestore" checks: read the flag, and when it is on, run a real
connectivity probe bounded at 1 s whose result is cached for 60 s (a health endpoint polled by a
load balancer must not turn into a stream of Agent Engine / Firestore calls). With a flag off,
no probe runs and the detail says so rather than implying the integration is live."""
from __future__ import annotations

import asyncio
import os
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from datetime import date
from pathlib import Path
from typing import Any

PROBE_TIMEOUT_S = 1.0
PROBE_TTL_S = 60.0

_POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix="health-probe")
_LOCK = threading.Lock()
_RESULTS: dict[str, tuple[float, dict[str, Any]]] = {}


def _probe(key: str, fn: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    now = time.monotonic()
    with _LOCK:
        hit = _RESULTS.get(key)
        if hit and now - hit[0] < PROBE_TTL_S:
            return hit[1] | {"probe_cached": True}
    t0 = time.perf_counter()
    try:
        out = _POOL.submit(fn).result(timeout=PROBE_TIMEOUT_S)
    except FutureTimeout:
        out = {"ok": False, "probe": f"timed out after {PROBE_TIMEOUT_S:.0f} s"}
    except Exception as e:  # the probe's own failure is the result, not a 500
        out = {"ok": False, "probe": f"failed: {type(e).__name__}: {str(e)[:160]}"}
    out = out | {"probe_ms": int((time.perf_counter() - t0) * 1000)}
    with _LOCK:
        _RESULTS[key] = (now, out)
    return out | {"probe_cached": False}


def reset_probe_cache() -> None:
    with _LOCK:
        _RESULTS.clear()


def sessions_check() -> dict[str, Any]:
    if os.environ.get("TAAL_SESSION_BACKEND") != "vertex":
        return {"ok": True, "backend": "in_memory", "detail": "InMemorySessionService: process-local, one per visitor sandbox; a restart forgets every conversation (TAAL_SESSION_BACKEND=vertex is off, so no probe runs)"}

    def fn() -> dict[str, Any]:
        from agents.vertex_sessions import build_session_service

        service = build_session_service()
        # A get for an id nobody creates: a round trip to the Agent Engine that must answer
        # "no such session" (None), never an error.
        found = asyncio.run(service.get_session(app_name="taal_customer", user_id="health-probe", session_id="health-probe:web"))
        return {"ok": True, "probe": "Agent Engine answered a session lookup" + (" (probe session unexpectedly exists)" if found is not None else "")}

    engine = os.environ.get("TAAL_AGENT_ENGINE_ID", "<unset>")
    res = _probe("sessions", fn)
    return {"ok": res["ok"], "backend": "vertex_ai_sessions", "agent_engine_id": engine, **{k: v for k, v in res.items() if k != "ok"},
            "detail": ("VertexAiSessionService on Agent Engine " + engine + ": sessions keyed per visitor and customer, kept across restarts") if res["ok"] else "TAAL_SESSION_BACKEND=vertex but the Agent Engine probe failed; chat turns will fail until it answers"}


def firestore_check(base_root: Path, clock_date: date, manifest_ok: bool) -> dict[str, Any]:
    from agents.gate import firestore_cache as fc

    if not fc.firestore_cache_enabled():
        return {"ok": manifest_ok, "backend": "local_store", "detail": "serving cache off (TAAL_SERVING_CACHE unset): every chat read goes to the visitor's own store; no probe runs. Firestore here holds practitioner feedback only (see feedback_store)"}

    snap = fc.snapshot_id(base_root)

    def fn() -> dict[str, Any]:
        from agents.gate.config import load_tenant

        cache = fc.build_cache(load_tenant().tenant_id)
        meta = cache.get_meta()
        if meta is None:
            return {"ok": False, "probe": "Firestore answered, but no mirror has been written (serving_meta missing): every read falls back to the store"}
        current = meta.get("snapshot_id") == snap and meta.get("as_of") == clock_date.isoformat()
        return {"ok": current, "probe": "Firestore answered", "mirror": {k: meta.get(k) for k in ("as_of", "snapshot_id", "mirrored_at", "counts")},
                "mirror_current": current}

    res = _probe("firestore", fn)
    detail = ("Firestore serving cache on: stock and customer profiles read from Firestore when the visitor has not changed them; consent and offers always from the visitor's store"
              if res["ok"] else "TAAL_SERVING_CACHE=firestore but the cache is not usable (see probe): chat falls back to the store, correct but uncached")
    return {"ok": res["ok"], "backend": "firestore", "serving_snapshot_id": snap, **{k: v for k, v in res.items() if k != "ok"}, "reads": fc.STATS.snapshot(), "detail": detail}
