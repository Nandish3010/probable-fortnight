"""Taal API (FastAPI) for the web app and the judge-mode landing. Contract: docs/openapi.yaml
(generated from this app by `make openapi`; tests/api/test_contract.py fails on drift).

Every request runs against the visitor's sandbox (services/api/sandbox.py). Live calls: approve,
rerun, chat, capture, execution. Recorded fallbacks carry `source: recorded`.
"""
from __future__ import annotations

import asyncio
import hmac
import json
import os
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, Literal
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from agents.capture.vision import commit_rows, intake
from agents.customer.chat import run_chat_async
from agents.gate.config import load_models, load_tenant
from agents.gate.store import LocalStore, OverlayStore, load_catalogue
from agents.planner.run import DEFAULT_DEADLINE_S, make_run_id, run_planner, run_planner_async
from jobs.measure.run import run_measure
from services.feedback import intake as feedback_intake
from services.feedback.store import build_store as build_feedback_store
from services.feedback.store import feedback_backend
from services.feedback.summary import exclusion_config as feedback_exclusion_config
from services.feedback.summary import summarize as summarize_feedback

from .approve import WindowExpired
from .approve import approve as do_approve
from .health_probes import firestore_check, sessions_check
from .sandbox import base_dir, store_for, visitor_id

VERSION = "0.1.0"
app = FastAPI(title="Taal API", version=VERSION, description="Demand-shaping plays with a holdout: sense, plan, approve, engage, measure.")
# allow_origin_regex=r"https?://.*" with allow_credentials=True used to reflect literally any
# calling origin back with credentials enabled -- any site can make a credentialed
# cross-origin request (carrying the taal_visitor sandbox cookie) against this public,
# unauthenticated API from a victim's browser. Restricted to an explicit allowlist instead:
# TAAL_ALLOWED_ORIGINS (comma-separated) for the deployed taal-web origin(s) in production,
# defaulting to the local dev server only.
_default_origins = "http://localhost:3000,http://127.0.0.1:3000"
_allowed_origins = [o.strip() for o in os.environ.get("TAAL_ALLOWED_ORIGINS", _default_origins).split(",") if o.strip()]
app.add_middleware(CORSMiddleware, allow_origins=_allowed_origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


def _now() -> datetime:
    """Wall clock, unless TAAL_NOW pins it. The seeded demo tenant is a snapshot frozen at its
    manifest `as_of` (2026-09-12): play windows, sell-by countdowns and the approve -> re-forecast
    beat are all computed relative to now, so judge mode runs with the clock pinned to the
    snapshot date (DECISIONS §5.6) or the whole demo silently goes stale once the planted
    deadlines pass."""
    pinned = os.environ.get("TAAL_NOW")
    if pinned:
        return datetime.fromisoformat(pinned.replace("Z", "+00:00")).astimezone(UTC)
    return datetime.now(UTC)


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds").replace("+00:00", "Z")


def _play_json(row: dict[str, Any]) -> dict[str, Any]:
    return json.loads(row["play_json"]) if isinstance(row.get("play_json"), str) else row.get("play_json") or {}


def _as_of(store: LocalStore) -> date:
    mp = store.root / "manifest.json"
    if not mp.exists() and isinstance(store, OverlayStore):
        mp = store.base.root / "manifest.json"
    return date.fromisoformat(json.loads(mp.read_text(encoding="utf-8"))["as_of"]) if mp.exists() else date.today()


# ----------------------------------------------------------------------------- models

class ApproveRequest(BaseModel):
    play_id: str
    holdout_fraction: float | None = Field(default=None, ge=0.05, le=0.9)
    rationale: str | None = None
    edits: list[dict[str, Any]] | None = None
    approved_by: str | None = None


class ForecastPointOut(BaseModel):
    date: str
    baseline_p50: float
    play_p50: float
    p10: float
    p90: float


class PlayWindowOut(BaseModel):
    start: str
    end: str


class ForecastOut(BaseModel):
    run_id: str
    model: str
    latency_ms: int
    series: list[ForecastPointOut]
    writeoff_before_inr: float
    writeoff_after_inr: float
    play_window: PlayWindowOut


class AssignmentOut(BaseModel):
    treated_n: int
    holdout_n: int
    seed: str
    fraction: float
    eligible_n: int
    excluded_subscribers: int


class CopyOut(BaseModel):
    variants: int
    rejected: list[str]


class ApproveResponseOut(BaseModel):
    play_id: str
    status: str
    assignment: AssignmentOut
    offers_written: int
    regressor_rows_touched: int
    copy_: CopyOut = Field(alias="copy")  # "copy" shadows BaseModel.copy(); alias keeps the wire field name
    forecast: ForecastOut
    source: str
    elapsed_ms: int
    note: str | None = None

    model_config = {"populate_by_name": True}


class RerunRequest(BaseModel):
    gap_id: str
    policy_text: str
    policy_version: str | None = None


class RerunAccepted(BaseModel):
    """POST /rerun's 202 body: the planner keeps running on a worker thread after this response
    lands; poll `status_url` or follow `stream_url` for the outcome (DECISIONS: re-plan is
    asynchronous because a live model call takes 20-45s -- see _run_replan_worker)."""

    run_id: str
    status: Literal["running"]
    gap_id: str
    policy_version: str
    backend: str
    deadline_s: float
    stream_url: str
    status_url: str


class PlanRequest(BaseModel):
    gap_id: str


class ChatRequest(BaseModel):
    session_id: str = Field(pattern=r"^[A-Za-z0-9_-]+:(web|whatsapp)$")
    text: str = Field(max_length=2000)
    customer_id: str | None = None
    language: str | None = None


class CaptureRequest(BaseModel):
    node_id: str
    photo_ref: str | None = None
    image_data_url: str | None = None


class CaptureConfirmRequest(BaseModel):
    node_id: str
    photo_ref: str
    rows: list[dict[str, Any]]


class ExecutionRequest(BaseModel):
    play_id: str
    node_id: str
    steps_done: list[str]
    evidence_photo_data_url: str | None = None
    note: str | None = None


class PolicyUpdate(BaseModel):
    text: str
    policy_version: str


# ----------------------------------------------------------------------------- routes

# A generous per-visitor cap on the model-calling endpoints only (POST /plan, /rerun, /chat --
# each makes a real Gemini call, and taal-agents is deployed --allow-unauthenticated and stays
# reachable from submission into December). Read endpoints (/health, /gaps, /plays, ...) are
# never limited: they cost nothing and a judge may poll them. In-memory, per-process -- fine for
# a single Cloud Run instance at min-instances=0; would need a shared store (Firestore/Redis) to
# hold across multiple instances, not needed at this traffic level.
_RATE_LIMITS: dict[str, list[float]] = defaultdict(list)
_RATE_LIMIT_LOCK = threading.Lock()


def _rate_limit(request: Request, bucket: str, max_calls: int, window_s: float, who: str | None = None) -> None:
    """`who` overrides the per-visitor key, e.g. a fixed "all" for a process-wide cap that a
    client cannot dodge by rotating its X-Taal-Visitor header."""
    key = f"{bucket}:{who or visitor_id(request) or (request.client.host if request.client else 'unknown')}"
    now = time.time()
    with _RATE_LIMIT_LOCK:
        calls = _RATE_LIMITS[key]
        calls[:] = [t for t in calls if now - t < window_s]
        if len(calls) >= max_calls:
            raise HTTPException(429, f"rate limit: at most {max_calls} {bucket} calls per {int(window_s)}s per visitor; wait and retry")
        calls.append(now)


def _check_vertex(backend: str, models: dict[str, Any]) -> dict[str, Any]:
    """A real check, not an assertion: in vertex mode, resolve the configured model id and
    confirm ambient credentials and a project are present via google.auth.default(). This never
    calls generateContent -- a health endpoint that bills tokens and takes seconds is worse than
    one that under-claims -- so it cannot prove Gemini actually answers, only that the pieces
    needed to call it are in place."""
    model_id = models["ids"].get("flash")
    if backend == "stub":
        return {"ok": True, "detail": f"stub backend; no live Vertex call (model id if live: {model_id})"}
    if not model_id:
        return {"ok": False, "detail": "no model id configured under config/models.toml [ids].flash"}
    try:
        import google.auth

        _, project = google.auth.default()
        if not project:
            return {"ok": False, "detail": "google.auth.default() resolved no project"}
        return {"ok": True, "detail": f"credentials + project resolved (project={project}, model={model_id}); generateContent not called by this check"}
    except Exception as e:
        return {"ok": False, "detail": f"vertex credentials not resolvable: {e}"}


@app.get("/health")
def health(store: LocalStore = Depends(store_for)) -> dict[str, Any]:
    models = load_models()
    tenant = load_tenant()
    t = _iso(_now())
    runs = store.read("sense_runs")
    last = runs[-1] if runs else None
    backend = models["backend"]
    vertex_check = _check_vertex(backend, models)
    checks = {
        # LocalStore is the system of record for every read/write this endpoint makes, in both
        # backends -- gaps, plays, forecasts, sense_runs never touch BigQuery. The one real
        # bigquery.Client call in the codebase is jobs/sense/copy.py::generate_copy_bigquery,
        # fired from POST /approve (vertex backend only) to run AI.GENERATE_TABLE over the
        # `taal.<flash id>_remote` model for offer copy; this endpoint does not call it itself
        # (a health check that bills tokens and takes seconds is worse than one that under-claims).
        # A BigQueryStore class exists (agents/gate/bigquery_store.py, verified against real
        # BigQuery) but is not wired into store_for() below -- LocalStore/OverlayStore remains
        # the system of record for every read/write this endpoint makes. The one real
        # bigquery.Client call reachable from a running server is generate_copy_bigquery
        # (jobs/sense/copy.py), fired from POST /approve (vertex backend only) for offer copy.
        "bigquery": {"ok": bool(runs), "checked_at": t, "detail": "local store is the system of record here; the one real BigQuery call is AI.GENERATE_TABLE for copy generation on POST /approve (vertex backend), not checked by this endpoint"},
        # Firestore serving cache (agents/gate/firestore_cache.py): flag off -> no probe, honest
        # "off" wording; flag on -> a 1 s probe of the mirror's serving_meta doc (cached 60 s),
        # whether that mirror matches this image's snapshot and clock, and read/hit counters.
        "firestore": {"checked_at": t, **firestore_check(store.base.root if isinstance(store, OverlayStore) else store.root, _now().date(), (store.root / "manifest.json").exists() or isinstance(store, OverlayStore))},
        "vertex": {"ok": vertex_check["ok"], "checked_at": t, "detail": vertex_check["detail"]},
        # Session backend (agents/vertex_sessions.py): flag off -> in-memory, no probe; flag on ->
        # a 1 s Agent Engine session lookup (cached 60 s).
        "sessions": {"checked_at": t, **sessions_check()},
    }
    status = "ok" if all(c["ok"] for c in checks.values()) else "degraded"
    return {
        "status": status, "version": VERSION, "checks": checks, "backend": backend,
        "tenant": {"tenant_id": tenant.tenant_id, "name": "Kutumb Mart", "skus": len(store.read("products")), "nodes": len(store.read("nodes")), "customers": len(store.read("customers"))},
        "last_sense_run_at": last and last["as_of"], "last_sense_run_minutes": last and round(last["timing_ms"]["total"] / 60000, 2), "last_sense_run_id": last and last["run_id"],
        "sellby_rule": tenant.sellby_rule.version,
        # The server's own clock (wall clock, or TAAL_NOW when pinned for the demo tenant). The
        # web app uses this -- never the browser's local clock -- for any day-countdown math
        # (GapCard's daysUntil) so it matches the pinned dates baked into the seeded tenant.
        "server_now": t,
        # Where practitioner feedback is written (services/feedback/store.py). infra/feedback_smoke.sh
        # fails a deploy unless this reads "firestore": the container disk does not survive a restart.
        "feedback_store": feedback_backend(),
    }


@app.get("/gaps")
def gaps(node_id: str | None = None, type: str | None = None, limit: int = Query(50, ge=1, le=1000), store: LocalStore = Depends(store_for)) -> list[dict[str, Any]]:
    rows = store.read("gaps")
    if node_id:
        rows = [g for g in rows if g["node_id"] == node_id]
    if type:
        rows = [g for g in rows if g["type"] == type]
    rows.sort(key=lambda g: (-float(g["rupees_at_stake"]), g["gap_id"]))
    return rows[:limit]


@app.get("/gaps/{gap_id}")
def gap(gap_id: str, store: LocalStore = Depends(store_for)) -> dict[str, Any]:
    rows = store.find("gaps", gap_id=gap_id)
    if not rows:
        raise HTTPException(404, f"unknown gap {gap_id}")
    return rows[-1]


@app.get("/plays")
def plays(gap_id: str | None = None, status: str | None = None, store: LocalStore = Depends(store_for)) -> list[dict[str, Any]]:
    out = [_play_json(r) for r in store.read("plays")]
    if gap_id:
        out = [p for p in out if p.get("gap_id") == gap_id]
    if status:
        out = [p for p in out if p.get("status") == status]
    stake = {g["gap_id"]: float(g["rupees_at_stake"]) for g in store.read("gaps")}
    out.sort(key=lambda p: (-stake.get(p["gap_id"], 0.0), p["play_id"]))
    return out


@app.get("/plays/{play_id}")
def play(play_id: str, store: LocalStore = Depends(store_for)) -> dict[str, Any]:
    rows = store.find("plays", play_id=play_id)
    if not rows:
        raise HTTPException(404, f"unknown play {play_id}")
    return _play_json(rows[-1])


@app.post("/plan")
async def plan(req: PlanRequest, request: Request, store: LocalStore = Depends(store_for)) -> dict[str, Any]:
    # A planner run is a real Gemini call taking ~90-110s; a generous cap (a demo runs at most a
    # handful) still bounds an unauthenticated visitor's worst-case spend.
    _rate_limit(request, "plan", max_calls=20, window_s=900)
    try:
        out = await run_planner_async(store.root, req.gap_id) if not isinstance(store, OverlayStore) else await _plan_overlay(store, req.gap_id)
    except KeyError as e:
        raise HTTPException(404, str(e)) from e
    # `planner_source` ("model" vs "deterministic_fallback", set by run_planner_async) must never
    # be clobbered: a deterministic-fallback play is never presented as model output. `out` already
    # carries the planner's own provenance under "source" (agents/planner/run.py's PLAN_SOURCES,
    # e.g. "scripted_stub"); the response's "source" key is a pre-existing, unrelated contract (this
    # request hit the live endpoint, not a recorded fixture), so the planner's value is surfaced
    # separately as "plan_source" rather than silently overwritten by the union below.
    return {k: v for k, v in out.items() if k != "events"} | {"source": "live", "plan_source": out.get("source")}


async def _plan_overlay(store: OverlayStore, gap_id: str, policy_text: str | None = None, policy_version: str | None = None, salt: str = "", play_id: str | None = None) -> dict[str, Any]:
    """Planner against a visitor overlay: run with the overlay as the store root by materialising the tables it reads."""
    for t in ("gaps", "plays", "products", "nodes", "customers", "affinity", "consent", "segments", "estimator_priors", "play_assignments", "inventory_batches", "inbound", "order_lines", "play_outcomes", "sense_runs", "policy"):
        store._materialise(t)
    if not (store.root / "manifest.json").exists():
        (store.root / "manifest.json").write_bytes((store.base.root / "manifest.json").read_bytes())
    return await run_planner_async(store.root, gap_id, policy_text=policy_text, policy_version=policy_version, salt=salt, play_id=play_id)


@app.post("/approve", response_model=ApproveResponseOut)
def approve_play(req: ApproveRequest, store: LocalStore = Depends(store_for)) -> dict[str, Any]:
    try:
        return do_approve(store, load_tenant(), req.play_id, _now(), req.holdout_fraction, req.rationale, req.edits, req.approved_by or "judge", as_of=_as_of(store))
    except KeyError as e:
        raise HTTPException(404, f"unknown play {e}") from e
    except WindowExpired as e:
        raise HTTPException(409, str(e)) from e


# ----------------------------------------------------------------------------- async re-plan runs
#
# POST /rerun used to run the planner inline and only answer once it was done; with the real model
# a run takes 20-45s (agents/planner/agent.py prompt CHANGELOG), and awaiting that on the API's one
# event loop stalls every other coroutine sharing it -- /chat included. The planner call now runs
# on a worker thread from this small pool; `_RUNS` is how its outcome becomes visible (to GET
# /rerun/{run_id} and the live SSE stream below) before the caller re-reads it from the trace file
# (agents/gate/store.py's events/<run_id>.jsonl, which run_planner_async itself always ends with one
# `kind: run_summary` record for -- see `_run_summary_source`). Keyed by (visitor_id, run_id) so one
# visitor's runs are never visible to another; `_INFLIGHT` caps each visitor at one running re-plan
# at a time.
_REPLAN_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="replan")
_RUN_TTL_S = 30 * 60  # prune finished entries this long after they finish


@dataclass
class _RunEntry:
    visitor_id: str
    status: str  # "running" | "done" | "error"
    started_at: float
    finished_at: float | None = None
    result: dict[str, Any] | None = None


_RUNS: dict[tuple[str, str], _RunEntry] = {}
_INFLIGHT: dict[str, str] = {}  # visitor_id -> run_id, present only while that run is "running"
_RUNS_LOCK = threading.Lock()


def _prune_runs_locked() -> None:
    now = time.time()
    for key, entry in list(_RUNS.items()):
        if entry.finished_at is not None and now - entry.finished_at > _RUN_TTL_S:
            del _RUNS[key]


def _get_run_entry(vid: str | None, run_id: str) -> _RunEntry | None:
    if not vid:
        return None
    with _RUNS_LOCK:
        _prune_runs_locked()
        return _RUNS.get((vid, run_id))


def _finish_run(vid: str, run_id: str, status: str, result: dict[str, Any]) -> None:
    with _RUNS_LOCK:
        entry = _RUNS.get((vid, run_id))
        if entry is not None:
            entry.status = status
            entry.finished_at = time.time()
            entry.result = result
        if _INFLIGHT.get(vid) == run_id:
            del _INFLIGHT[vid]


def _run_replan_worker(store: LocalStore, vid: str, gap_id: str, policy_text: str, version: str, salt: str, run_id: str, play_id: str | None = None) -> None:
    """Runs on a `_REPLAN_EXECUTOR` thread, never on the API's event loop (DECISIONS: this is CPU-
    bound tool work, not I/O). Mirrors the two sync call shapes /plan already uses: an OverlayStore
    goes through `_plan_overlay` (materialise, then plan) via `asyncio.run`; a bare LocalStore goes
    through the plain sync `run_planner` wrapper. run_planner_async itself appends the trace's one
    terminal `kind: run_summary` record (agents/planner/run.py) before returning, so this worker
    never writes one of its own -- doing so would duplicate it."""
    try:
        if isinstance(store, OverlayStore):
            out = asyncio.run(_plan_overlay(store, gap_id, policy_text, version, salt=salt, play_id=play_id))
        else:
            out = run_planner(store.root, gap_id, policy_text=policy_text, policy_version=version, salt=salt, play_id=play_id)
    except Exception as e:
        # A short message only -- never a stack trace, and never anything from the environment.
        _finish_run(vid, run_id, "error", {"run_id": run_id, "status": "error", "error": str(e)[:300]})
        return
    result = {
        "run_id": out["run_id"], "status": out["status"], "play": out["play"], "policy_version": out.get("policy_version", version),
        "iterations": out["iterations"], "elapsed_ms": out.get("elapsed_ms"), "source": out.get("source"),
        "planner_source": out.get("planner_source"), "fallback_reason": out.get("fallback_reason"),
    }
    _finish_run(vid, run_id, "done", result)


def _live_play_id(store: LocalStore, gap_id: str, version: str) -> str:
    taken = {r["play_id"] for r in store.find("plays", gap_id=gap_id)}
    base = f"play_{gap_id.removeprefix('gap_')}_{version}_live"
    return next(pid for n in range(1, 1000) if (pid := base if n == 1 else f"{base}{n}") not in taken)


@app.post("/rerun", response_model=RerunAccepted, status_code=202)
async def rerun(req: RerunRequest, request: Request, store: LocalStore = Depends(store_for)) -> dict[str, Any]:
    _rate_limit(request, "plan", max_calls=20, window_s=900)  # same planner call as /plan; shares its bucket
    if not store.find("gaps", gap_id=req.gap_id):
        raise HTTPException(404, f"unknown gap {req.gap_id}")
    vid = visitor_id(request)  # store_for already requires this for a mutating request; never None here
    # A run under unchanged policy text (a live run on the policy as it stands) reuses the current
    # version and writes no row; only different text, or an explicit `policy_version`, makes one.
    current = _current_policy(store)
    reuse = req.policy_version is None and req.policy_text.strip() == current["text"].strip()
    version = current["policy_version"] if reuse else (req.policy_version or f"v{len(store.read('policy')) + 2}")
    # A reused version would file the play under the recorded play's id and overwrite it, so a live
    # run gets its own: play_<gap>_<version>_live, then _live2, _live3, ...
    play_id = _live_play_id(store, req.gap_id, version) if reuse else None
    salt = uuid4().hex[:8]  # a fresh salt per async run so re-posting the same policy_version never collides with a run still in flight
    run_id = make_run_id(req.gap_id, version, salt)
    with _RUNS_LOCK:
        _prune_runs_locked()
        running = _INFLIGHT.get(vid)
        if running is not None:
            raise HTTPException(409, f"a re-plan is already running for this visitor: {running}")
        _RUNS[(vid, run_id)] = _RunEntry(visitor_id=vid, status="running", started_at=time.time())
        _INFLIGHT[vid] = run_id
    try:
        if not reuse:
            store.append("policy", [{"policy_version": version, "text": req.policy_text, "updated_at": _iso(_now())}])
        _REPLAN_EXECUTOR.submit(_run_replan_worker, store, vid, req.gap_id, req.policy_text, version, salt, run_id, play_id)
    except Exception:
        # Neither the policy append nor the submit actually started a run -- undo the claim above
        # so this visitor is not stuck seeing 409 ("already running") for a run that never runs,
        # until the process restarts and clears `_INFLIGHT` for them.
        with _RUNS_LOCK:
            _RUNS.pop((vid, run_id), None)
            if _INFLIGHT.get(vid) == run_id:
                del _INFLIGHT[vid]
        raise
    backend = load_models()["backend"]
    deadline_s = float(os.environ.get("TAAL_PLANNER_DEADLINE_S", DEFAULT_DEADLINE_S))
    return {
        "run_id": run_id, "status": "running", "gap_id": req.gap_id, "policy_version": version, "backend": backend,
        "deadline_s": deadline_s, "stream_url": f"/events/{run_id}/stream", "status_url": f"/rerun/{run_id}",
    }


@app.get("/rerun/{run_id}")
def rerun_status(run_id: str, request: Request) -> dict[str, Any]:
    entry = _get_run_entry(visitor_id(request), run_id)
    if entry is None:
        raise HTTPException(404, f"no re-plan run {run_id} for this visitor")
    return {
        "run_id": run_id, "status": entry.status,
        "started_at": _iso(datetime.fromtimestamp(entry.started_at, UTC)),
        "finished_at": _iso(datetime.fromtimestamp(entry.finished_at, UTC)) if entry.finished_at else None,
        "result": entry.result,
    }


def _current_policy(store: LocalStore) -> dict[str, Any]:
    rows = store.read("policy")
    if rows:
        return rows[-1]
    t = load_tenant()
    return {"policy_version": t.policy_version, "text": t.policy_text.strip(), "updated_at": None}


@app.get("/policy")
def policy(store: LocalStore = Depends(store_for)) -> dict[str, Any]:
    return _current_policy(store)


@app.put("/policy")
def put_policy(req: PolicyUpdate, store: LocalStore = Depends(store_for)) -> dict[str, Any]:
    row = {"policy_version": req.policy_version, "text": req.text, "updated_at": _iso(_now())}
    store.append("policy", [row])
    return row


def _run_summary_source(evs: list[dict[str, Any]]) -> str | None:
    """The `source` of the trace's `kind: run_summary` record, else None. run_planner_async
    (agents/planner/run.py) ends every run -- /plan, /rerun, and a seeded recording alike -- with
    exactly one such record, so this is the planner's own account of where the play came from, not
    something this API computes or appends itself."""
    summary = next((e for e in reversed(evs) if e.get("kind") == "run_summary"), None)
    return summary.get("source") if summary else None


@app.get("/events/{run_id}")
def events(run_id: str, store: LocalStore = Depends(store_for)) -> dict[str, Any]:
    evs = store.read_events(run_id)
    if not evs and isinstance(store, OverlayStore):
        evs = store.base.read_events(run_id)
    if not evs:
        raise HTTPException(404, f"no events for {run_id}")
    return {
        "run_id": run_id, "recorded_at": _iso(datetime.fromtimestamp(evs[0]["timestamp"], UTC)) if evs[0].get("timestamp") else None,
        "source": _run_summary_source(evs), "events": evs,
    }


_LIVE_POLL_S = 0.25
_LIVE_KEEPALIVE_S = 10.0


async def _live_follow_events(store: LocalStore, vid: str, run_id: str, request: Request):
    """Server-sent events for a run this API kicked off asynchronously (POST /rerun): poll the
    visitor's own trace file and forward each new record as soon as it lands, so the web app can
    show a live-updating trace instead of only a final result 20-45s later with the real model.
    An async generator throughout (asyncio.sleep only) so this never blocks the event loop either.
    """
    sent = 0
    last_sent_at = time.monotonic()
    try:
        while True:
            if await request.is_disconnected():
                return
            evs = store.read_events(run_id)
            for e in evs[sent:]:
                yield f"data: {json.dumps(e, ensure_ascii=False)}\n\n"
            if len(evs) > sent:
                sent = len(evs)
                last_sent_at = time.monotonic()
            entry = _get_run_entry(vid, run_id)
            if entry is None or entry.status != "running":
                # flush anything written between the last read above and now, then close
                evs = store.read_events(run_id)
                for e in evs[sent:]:
                    yield f"data: {json.dumps(e, ensure_ascii=False)}\n\n"
                result = (entry.result if entry else None) or {"run_id": run_id, "status": "error", "error": "run no longer tracked"}
                yield f"event: done\ndata: {json.dumps(result, ensure_ascii=False)}\n\n"
                return
            if time.monotonic() - last_sent_at >= _LIVE_KEEPALIVE_S:
                yield ": keepalive\n\n"
                last_sent_at = time.monotonic()
            await asyncio.sleep(_LIVE_POLL_S)
    except asyncio.CancelledError:
        return


@app.get("/events/{run_id}/stream")
def events_stream(run_id: str, request: Request, speed: float = Query(4.0, ge=0.1, le=100), store: LocalStore = Depends(store_for)) -> StreamingResponse:
    vid = visitor_id(request)
    entry = _get_run_entry(vid, run_id)
    if entry is not None:
        # `vid` cannot be None here: _get_run_entry(None, ...) always returns None.
        return StreamingResponse(_live_follow_events(store, vid, run_id, request), media_type="text/event-stream")

    # Not a run this session is tracking for the calling visitor: today's replay behaviour for a
    # recorded trace, completely unchanged (including the same 404 when there are no events, and
    # the same visitor-scoped-then-base-tenant-fallback read that keeps another visitor's -- or a
    # headerless caller's -- in-flight /rerun run invisible here too).
    evs = store.read_events(run_id) or (store.base.read_events(run_id) if isinstance(store, OverlayStore) else [])
    if not evs:
        raise HTTPException(404, f"no events for {run_id}")

    def gen():
        last = 0
        for e in evs:
            wait = max(0, e.get("ts_offset_ms", 0) - last) / 1000.0 / speed
            if wait > 0:
                time.sleep(min(wait, 2.0))
            last = e.get("ts_offset_ms", 0)
            yield f"data: {json.dumps(e, ensure_ascii=False)}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.post("/chat")
async def chat(req: ChatRequest, request: Request, store: LocalStore = Depends(store_for)) -> StreamingResponse:
    # A generous cap for a single-visitor demo (a scripted walkthrough sends well under a dozen
    # messages); wide enough that no legitimate judge session is at risk of tripping it.
    _rate_limit(request, "chat", max_calls=60, window_s=900)
    envelopes = await run_chat_async(store, req.session_id, req.text, req.customer_id, now_iso=_iso(_now()), visitor_id=visitor_id(request))
    if "application/json" in (request.headers.get("accept") or ""):
        from fastapi.responses import JSONResponse

        return JSONResponse(envelopes)

    async def gen():
        for env in envelopes:
            yield f"data: {json.dumps(env, ensure_ascii=False)}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.post("/reset")
async def reset(request: Request, store: LocalStore = Depends(store_for)) -> dict[str, Any]:
    vid = visitor_id(request)
    if isinstance(store, OverlayStore):
        from agents.chat_runtime import forget_persisted_sessions
        from agents.customer.chat import APP as CUSTOMER_APP
        from agents.customer.chat import reset_sessions

        # Before store.reset(): the visitor's conversations rows name the persisted (Vertex)
        # sessions to delete. Only this visitor's runners are dropped, not every visitor's.
        await forget_persisted_sessions(store, vid, [CUSTOMER_APP])
        store.reset()
        reset_sessions(store)
        return {"ok": True, "namespace": vid, "restored_from": "base tenant snapshot"}
    return {"ok": False, "namespace": "base", "restored_from": None, "detail": "no visitor id: the base tenant is never reset through the API"}


@app.post("/capture")
def capture(req: CaptureRequest, store: LocalStore = Depends(store_for)) -> dict[str, Any]:
    if not req.photo_ref and not req.image_data_url:
        raise HTTPException(422, "photo_ref or image_data_url required")
    return intake(store, req.node_id, req.photo_ref, req.image_data_url)


@app.post("/capture/confirm")
def capture_confirm(req: CaptureConfirmRequest, store: LocalStore = Depends(store_for)) -> dict[str, Any]:
    result = commit_rows(store, req.node_id, req.rows, req.photo_ref, _iso(_now()))
    written = result["written"]
    new_gaps = _redetect_gaps(store, req.node_id) if written else []
    # ok=false when rows were submitted but every one was skipped (nothing to write is not a
    # success); a request with no rows at all is a trivial, real no-op.
    ok = bool(written) or not req.rows
    return {"ok": ok, "written": len(written), "batches": written, "skipped": result["skipped"], "gaps_refreshed": len(new_gaps)}


def _redetect_gaps(store: LocalStore, node_id: str) -> list[dict[str, Any]]:
    """On-demand Sense for one node after a photo intake (DECISIONS §2.2: nightly + on demand)."""
    from jobs.sense.gaps import detect

    runs = store.read("sense_runs")
    if not runs:
        return []
    run_id = runs[-1]["run_id"]
    forecasts = [r for r in store.read("forecasts") if r["node_id"] == node_id and not r.get("includes_plays")]
    fresh = [g for g in detect(store, forecasts, _as_of(store), load_tenant(), run_id) if g["node_id"] == node_id]
    kept = [g for g in store.read("gaps") if g["node_id"] != node_id]
    # gap_id is a deterministic hash of (type, sku, node, batch), so a play's gap_id linkage
    # survives untouched here even though the gap's own numbers do get refreshed -- that refresh
    # is the entire point of an on-demand redetect (a new pallet lands, or new customer_requests
    # rows should enrich stockout_risk/unmet_demand evidence); serving the old, stale snapshot
    # back out would make this endpoint a no-op for every gap that already existed.
    store.write("gaps", kept + fresh)
    return fresh


@app.get("/outcomes")
def outcomes(store: LocalStore = Depends(store_for)) -> list[dict[str, Any]]:
    rows = store.read("play_outcomes")
    plays_by = {r["play_id"]: _play_json(r) for r in store.read("plays")}
    by_play: dict[str, dict[str, Any]] = {}
    for r in rows:
        p = plays_by.get(r["play_id"], {})
        o = by_play.setdefault(r["play_id"], {"play_id": r["play_id"], "sku": p.get("target", {}).get("sku"), "node_id": (p.get("target", {}).get("node_ids") or [None])[0], "mechanic": p.get("mechanic"), "status": r["status"], "measured_at": r["computed_at"], "min_treated_n": r["min_treated_n"], "data_label": os.environ.get("TAAL_OUTCOMES_LABEL", "SYNTHETIC"), "looker_url": os.environ.get("TAAL_LOOKER_URL")})
        arm = {"customers": r["customers"], "responders": r["responders"], "units": r["units_target_lot"], "revenue_inr": r["revenue"], "margin_inr": r["margin"], "discount_cost_inr": r["discount_cost"]}
        o[r["arm"]] = arm
        if r["arm"] == "treated" and r["status"] == "measured":
            o.update({"lift": r["lift"], "ci_low": r["ci_low"], "ci_high": r["ci_high"], "waste_avoided_inr": r["waste_avoided"], "margin_per_discount_rupee": r["net_margin_per_discount_inr"], "waste_kg_est": r["waste_kg_est"], "co2e_kg_est": r["co2e_kg_est"]})
    out = list(by_play.values())
    for o in out:
        o.setdefault("treated", {"customers": 0, "responders": 0, "units": 0, "revenue_inr": 0, "margin_inr": 0, "discount_cost_inr": 0})
        o.setdefault("holdout", {"customers": 0, "responders": 0, "units": 0, "revenue_inr": 0, "margin_inr": 0, "discount_cost_inr": 0})
    return out


@app.get("/outcomes/prior-update")
def outcomes_prior_update() -> dict[str, Any]:
    """The flagship play's estimator prior, before -> after one Measure run on SYNTHETIC orders
    (harness/prior_update_demo.py, run once when the tenant is built). Read from the base data
    dir, never a visitor sandbox, so every visitor sees the same result and Reset cannot change
    it; the base tenant's own estimator_priors are not updated by it."""
    p = base_dir() / "prior_update_demo.json"
    if not p.exists():
        raise HTTPException(404, "no prior update built; run python -m harness.prior_update_demo")
    return json.loads(p.read_text(encoding="utf-8"))


@app.get("/customers/demo")
def customers_demo(play_id: str = Query("play_chips_ds07_v1"), store: LocalStore = Depends(store_for)) -> list[dict[str, Any]]:
    """A curated picker for the web app: named personas with visibly different home stores and
    languages, plus one real customer who lands in the holdout arm of `play_id` -- computed from
    the play's own holdout seed and fraction, so it is correct whether or not the play has been
    approved yet, and never made up. Lets a judge see the differentiation the system is built on:
    a holdout customer's chat never mentions the offer other customers get."""
    from agents.gate.assignment import assign_arm
    from agents.planner.context import PlannerContext
    from agents.planner.tools import audience_customer_ids

    tenant = load_tenant()
    customers = {c["customer_id"]: c for c in store.read("customers")}
    out: list[dict[str, Any]] = []
    for cid, note in (("CUST-MEENA", "treated on the chips play once approved"), ("CUST-RAVI", "different store and language; premium tea affinity")):
        c = customers.get(cid)
        if c:
            out.append({"customer_id": cid, "display_name": c.get("display_name") or cid, "home_node_id": c["home_node_id"], "language": c.get("language", "en"), "role": "sample", "note": note})
    play_rows = store.find("plays", play_id=play_id)
    if play_rows:
        play = _play_json(play_rows[-1])
        pctx = PlannerContext.__new__(PlannerContext)
        pctx.store, pctx.tenant, pctx.run_id = store, tenant, "customers-demo"
        pctx.products = load_catalogue(store)
        pctx.nodes = {n["node_id"]: n for n in store.read("nodes")}
        ids = audience_customer_ids(pctx, play["target"]["sku"], play["target"]["node_ids"], play["audience"]["segment_ids"])
        seed, fraction = play["holdout"]["seed"], float(play["holdout"]["fraction"])
        holdout_id = next((cid for cid in ids if cid not in ("CUST-MEENA", "CUST-RAVI") and assign_arm(cid, seed, fraction) == "holdout"), None)
        if holdout_id:
            c = customers[holdout_id]
            out.append({"customer_id": holdout_id, "display_name": c.get("display_name") or holdout_id, "home_node_id": c["home_node_id"], "language": c.get("language", "en"), "role": "holdout", "note": f"holdout arm on {play_id}: never receives this offer, even after it is approved"})
    return out


@app.post("/measure")
def measure(store: LocalStore = Depends(store_for)) -> dict[str, Any]:
    if isinstance(store, OverlayStore):
        for t in ("plays", "play_assignments", "order_lines", "play_outcomes", "estimator_priors", "products"):
            store._materialise(t)
    return run_measure(store.root, computed_at=_iso(_now()))


@app.post("/execution")
def execution(req: ExecutionRequest, store: LocalStore = Depends(store_for)) -> dict[str, Any]:
    now = _now()
    seq = len(store.read("execution_events")) + 1
    eid = f"exec_{req.play_id}_{seq}"
    store.append("execution_events", [{"tenant_id": load_tenant().tenant_id, "run_id": eid, "seq": seq, "ts": _iso(now), "ts_offset_ms": 0, "agent": "phone_view", "event_type": "steps_done", "payload": json.dumps({"play_id": req.play_id, "node_id": req.node_id, "steps_done": req.steps_done, "evidence_photo": bool(req.evidence_photo_data_url), "note": req.note})}])
    return {"ok": True, "execution_id": eid, "recorded_at": _iso(now)}


@app.get("/sense/last")
def sense_last(store: LocalStore = Depends(store_for)) -> dict[str, Any]:
    runs = store.read("sense_runs")
    if not runs:
        raise HTTPException(404, "no sense run yet")
    return runs[-1]


# ----------------------------------------------------------------------------- practitioner feedback
#
# The one real dataset in this service (services/feedback/__init__.py). None of these routes take
# store_for: feedback never reads or writes the demo tenant or a visitor sandbox, so "Reset demo
# data" cannot reach it. POST /feedback is public and unauthenticated (practitioners open a shared
# link on their phones); reading aggregates and deleting a response need the admin token, which
# lives in Secret Manager and reaches the container only as TAAL_FEEDBACK_ADMIN_TOKEN.

def _feedback_openapi_body() -> dict[str, Any]:
    body = {k: v for k, v in feedback_intake.schema().items() if k not in ("$schema", "$id", "$defs")}
    return {"requestBody": {"required": True, "content": {"application/json": {"schema": body}}}}


def _require_feedback_admin(request: Request) -> None:
    _rate_limit(request, "feedback_admin", max_calls=30, window_s=900)
    token = os.environ.get("TAAL_FEEDBACK_ADMIN_TOKEN")
    if not token:
        raise HTTPException(503, "feedback results are not enabled on this server (TAAL_FEEDBACK_ADMIN_TOKEN is unset)")
    auth = request.headers.get("authorization") or ""
    given = auth[7:].strip() if auth[:7].lower() == "bearer " else ""
    if not given or not hmac.compare_digest(given.encode(), token.encode()):
        raise HTTPException(401, "a valid admin token is required", headers={"WWW-Authenticate": "Bearer"})


@app.get("/feedback/form")
def feedback_form() -> dict[str, Any]:
    """The questionnaire (config/feedback_form.json), so wording changes need no web rebuild."""
    return feedback_intake.form()


@app.post("/feedback", openapi_extra=_feedback_openapi_body())
async def submit_feedback(request: Request) -> dict[str, Any]:
    # Per visitor, then process-wide: the per-visitor key is a client-chosen header, so the second
    # cap is what actually bounds a scripted flood. In-memory and per Cloud Run instance, like the
    # other limits in this file.
    _rate_limit(request, "feedback", max_calls=20, window_s=3600)
    _rate_limit(request, "feedback", max_calls=300, window_s=3600, who="all")
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > feedback_intake.MAX_BODY_BYTES:
        raise HTTPException(413, f"request body over {feedback_intake.MAX_BODY_BYTES} bytes")
    raw = bytearray()
    async for chunk in request.stream():
        raw += chunk
        if len(raw) > feedback_intake.MAX_BODY_BYTES:
            raise HTTPException(413, f"request body over {feedback_intake.MAX_BODY_BYTES} bytes")
    try:
        doc = feedback_intake.parse(bytes(raw))
    except feedback_intake.Rejected as e:
        raise HTTPException(e.status, e.detail) from e
    response_id = feedback_intake.new_response_id()
    if doc is None:
        # Honeypot filled: answer exactly as for a real submission and store nothing.
        return {"ok": True, "response_id": response_id}
    # Real wall clock, never the TAAL_NOW pin the demo tenant runs under.
    record, contact = feedback_intake.to_record(doc, response_id, datetime.now(UTC))
    try:
        build_feedback_store().add(record, contact)
    except Exception as e:
        raise HTTPException(503, "your response could not be saved; please try again in a minute") from e
    return {"ok": True, "response_id": response_id}


@app.get("/feedback/summary")
def feedback_summary(request: Request) -> dict[str, Any]:
    """Aggregates only -- the same summarize() and the same config/feedback_exclusions.json the
    committed harness command uses. Never reads the contacts collection."""
    _require_feedback_admin(request)
    now = datetime.now(UTC)
    return summarize_feedback(build_feedback_store().responses(), feedback_intake.form(), _iso(now), **feedback_exclusion_config())


@app.delete("/feedback/{response_id}")
def delete_feedback(response_id: str, request: Request) -> dict[str, Any]:
    """Deletion on request (docs/privacy.md): removes the answers and any contact details."""
    _require_feedback_admin(request)
    if not feedback_intake.RESPONSE_ID_RE.match(response_id):
        raise HTTPException(422, "response_id is 32 lowercase hex characters")
    if not build_feedback_store().delete(response_id):
        raise HTTPException(404, "no response with that id")
    return {"deleted": True, "response_id": response_id}
