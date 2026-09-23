"""Taal API (FastAPI) for the web app and the judge-mode landing. Contract: docs/openapi.yaml
(generated from this app by `make openapi`; tests/api/test_contract.py fails on drift).

Every request runs against the visitor's sandbox (services/api/sandbox.py). Live calls: approve,
rerun, chat, capture, execution. Recorded fallbacks carry `source: recorded`.
"""
from __future__ import annotations

import json
import os
import threading
import time
from collections import defaultdict
from datetime import UTC, date, datetime
from typing import Any, Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from agents.capture.vision import commit_rows, intake
from agents.customer.chat import run_chat_async
from agents.gate.config import load_models, load_tenant
from agents.gate.store import LocalStore, OverlayStore, load_catalogue
from agents.planner.run import run_planner_async
from agents.stylist.chat import run_stylist_chat_async
from jobs.measure.run import run_measure
from jobs.sense.trends import build_style_trends

from .approve import approve as do_approve
from .sandbox import store_for, visitor_id

VERSION = "0.1.0"
app = FastAPI(title="Taal API", version=VERSION, description="Demand-shaping plays with a holdout: sense, plan, approve, engage, measure.")

# `allow_origin_regex=r"https?://.*"` used to reflect ANY origin while `allow_credentials=True`
# (the visitor sandbox cookie set in sandbox.py IS a credential) -- that lets any website read a
# visitor's sandbox by riding their cookie. TAAL_ALLOWED_ORIGINS (comma-separated) is set to the
# deployed taal-web URL by infra/deploy.sh once that URL is known; the localhost defaults cover
# `make demo` / `make web`.
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


class PlanRequest(BaseModel):
    gap_id: str


class ChatRequest(BaseModel):
    session_id: str = Field(pattern=r"^[A-Za-z0-9_-]+:(web|whatsapp)$")
    text: str = Field(max_length=2000)
    customer_id: str | None = None
    language: str | None = None
    specialist: Literal["customer", "stylist"] = "customer"
    image_data_url: str | None = Field(default=None, max_length=3_000_000)
    photo_ref: str | None = None
    image_kind: Literal["garment", "selfie"] = "garment"


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


def _rate_limit(request: Request, bucket: str, max_calls: int, window_s: float) -> None:
    key = f"{bucket}:{visitor_id(request) or request.client.host if request.client else 'unknown'}"
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
        "bigquery": {"ok": bool(runs), "checked_at": t, "detail": "local store is the system of record here; the one real BigQuery call is AI.GENERATE_TABLE for copy generation on POST /approve (vertex backend), not checked by this endpoint"},
        "firestore": {"ok": (store.root / "manifest.json").exists() or isinstance(store, OverlayStore), "checked_at": t, "detail": "local store is the system of record here; Firestore is provisioned in production but this process never queries it"},
        "vertex": {"ok": vertex_check["ok"], "checked_at": t, "detail": vertex_check["detail"]},
        # Both agents/customer/chat.py and agents/planner/run.py construct InMemoryRunner
        # unconditionally -- VertexAiSessionService is not wired up in either backend.
        "sessions": {"ok": True, "checked_at": t, "detail": "InMemorySessionService (process-local; not persisted across restarts, in either backend)"},
    }
    status = "ok" if all(c["ok"] for c in checks.values()) else "degraded"
    return {
        "status": status, "version": VERSION, "checks": checks, "backend": backend,
        "tenant": {"tenant_id": tenant.tenant_id, "name": "Kutumb Mart", "skus": len(store.read("products")), "nodes": len(store.read("nodes")), "customers": len(store.read("customers"))},
        "last_sense_run_at": last and last["as_of"], "last_sense_run_minutes": last and round(last["timing_ms"]["total"] / 60000, 2), "last_sense_run_id": last and last["run_id"],
        "sellby_rule": tenant.sellby_rule.version,
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
    # be clobbered: a deterministic-fallback play is never presented as model output.
    return {k: v for k, v in out.items() if k != "events"} | {"source": "live"}


async def _plan_overlay(store: OverlayStore, gap_id: str, policy_text: str | None = None, policy_version: str | None = None) -> dict[str, Any]:
    """Planner against a visitor overlay: run with the overlay as the store root by materialising the tables it reads."""
    for t in ("gaps", "plays", "products", "nodes", "customers", "affinity", "consent", "segments", "estimator_priors", "play_assignments", "inventory_batches", "inbound", "order_lines", "play_outcomes", "sense_runs", "policy"):
        store._materialise(t)
    if not (store.root / "manifest.json").exists():
        (store.root / "manifest.json").write_bytes((store.base.root / "manifest.json").read_bytes())
    return await run_planner_async(store.root, gap_id, policy_text=policy_text, policy_version=policy_version)


@app.post("/approve", response_model=ApproveResponseOut)
def approve_play(req: ApproveRequest, store: LocalStore = Depends(store_for)) -> dict[str, Any]:
    try:
        return do_approve(store, load_tenant(), req.play_id, _now(), req.holdout_fraction, req.rationale, req.edits, req.approved_by or "judge", as_of=_as_of(store))
    except KeyError as e:
        raise HTTPException(404, f"unknown play {e}") from e


@app.post("/rerun")
async def rerun(req: RerunRequest, request: Request, store: LocalStore = Depends(store_for)) -> dict[str, Any]:
    _rate_limit(request, "plan", max_calls=20, window_s=900)  # same planner call as /plan; shares its bucket
    version = req.policy_version or f"v{len(store.read('policy')) + 2}"
    store.append("policy", [{"policy_version": version, "text": req.policy_text, "updated_at": _iso(_now())}])
    try:
        out = await (_plan_overlay(store, req.gap_id, req.policy_text, version) if isinstance(store, OverlayStore) else run_planner_async(store.root, req.gap_id, policy_text=req.policy_text, policy_version=version))
    except KeyError as e:
        raise HTTPException(404, str(e)) from e
    return {"run_id": out["run_id"], "play": out["play"], "policy_version": version, "status": out["status"], "iterations": out["iterations"], "source": "live", "planner_source": out.get("planner_source"), "fallback_reason": out.get("fallback_reason")}


@app.get("/policy")
def policy(store: LocalStore = Depends(store_for)) -> dict[str, Any]:
    rows = store.read("policy")
    if rows:
        return rows[-1]
    t = load_tenant()
    return {"policy_version": t.policy_version, "text": t.policy_text.strip(), "updated_at": None}


@app.put("/policy")
def put_policy(req: PolicyUpdate, store: LocalStore = Depends(store_for)) -> dict[str, Any]:
    row = {"policy_version": req.policy_version, "text": req.text, "updated_at": _iso(_now())}
    store.append("policy", [row])
    return row


@app.get("/events/{run_id}")
def events(run_id: str, store: LocalStore = Depends(store_for)) -> dict[str, Any]:
    evs = store.read_events(run_id)
    if not evs and isinstance(store, OverlayStore):
        evs = store.base.read_events(run_id)
    if not evs:
        raise HTTPException(404, f"no events for {run_id}")
    return {"run_id": run_id, "recorded_at": _iso(datetime.fromtimestamp(evs[0]["timestamp"], UTC)) if evs[0].get("timestamp") else None, "events": evs}


@app.get("/events/{run_id}/stream")
def events_stream(run_id: str, speed: float = Query(4.0, ge=0.1, le=100), store: LocalStore = Depends(store_for)) -> StreamingResponse:
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
async def chat(req: ChatRequest, request: Request, response: Response, store: LocalStore = Depends(store_for)) -> StreamingResponse:
    # A generous cap for a single-visitor demo (a scripted walkthrough sends well under a dozen
    # messages); wide enough that no legitimate judge session is at risk of tripping it. Shared
    # by both specialists since they're the same endpoint.
    _rate_limit(request, "chat", max_calls=60, window_s=900)
    if req.specialist == "stylist":
        envelopes = await run_stylist_chat_async(store, req.session_id, req.text, req.customer_id, now_iso=_iso(_now()), image_data_url=req.image_data_url, photo_ref=req.photo_ref, image_kind=req.image_kind)
    else:
        if req.image_data_url or req.photo_ref:
            raise HTTPException(422, "photo input is a stylist feature; set specialist=stylist")
        envelopes = await run_chat_async(store, req.session_id, req.text, req.customer_id, now_iso=_iso(_now()))
    # `store_for` (a dependency, injecting its own `response: Response`) may have just set the
    # visitor cookie on THIS endpoint's headerless first call -- but this handler returns its own
    # JSONResponse/StreamingResponse instance rather than a plain dict, and FastAPI does not merge
    # an injected Response's headers into an endpoint-returned Response (verified directly: a
    # cookie set on the dependency's `response` is silently dropped when the endpoint returns its
    # own Response object). Copy it across explicitly so a visitor's very first call, if it
    # happens to be /chat, still gets a session cookie back.
    if "application/json" in (request.headers.get("accept") or ""):
        from fastapi.responses import JSONResponse

        out = JSONResponse(envelopes)
        out.raw_headers.extend(response.raw_headers)
        return out

    async def gen():
        for env in envelopes:
            yield f"data: {json.dumps(env, ensure_ascii=False)}\n\n"

    out = StreamingResponse(gen(), media_type="text/event-stream")
    out.raw_headers.extend(response.raw_headers)
    return out


@app.post("/reset")
def reset(request: Request, store: LocalStore = Depends(store_for)) -> dict[str, Any]:
    if isinstance(store, OverlayStore):
        # `store` may be a sandbox `store_for` just minted for this headerless request (a cookie
        # it does not carry itself -- that cookie is on the outgoing response). Read the visitor
        # id back off the store's own overlay directory rather than re-parsing the request, so
        # this reports the sandbox that was actually reset instead of silently reporting None.
        vid = store.root.name
        store.reset()
        from agents.customer.chat import reset_sessions
        from agents.stylist.chat import reset_sessions as reset_stylist_sessions

        reset_sessions()
        reset_stylist_sessions()
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
        for t in ("plays", "play_assignments", "order_lines", "play_outcomes", "estimator_priors", "products", "apparel_products"):
            store._materialise(t)
    return run_measure(store.root, computed_at=_iso(_now()))


@app.post("/execution")
def execution(req: ExecutionRequest, store: LocalStore = Depends(store_for)) -> dict[str, Any]:
    now = _now()
    seq = len(store.read("execution_events")) + 1
    eid = f"exec_{req.play_id}_{seq}"
    store.append("execution_events", [{"tenant_id": load_tenant().tenant_id, "run_id": eid, "seq": seq, "ts": _iso(now), "ts_offset_ms": 0, "agent": "phone_view", "event_type": "steps_done", "payload": json.dumps({"play_id": req.play_id, "node_id": req.node_id, "steps_done": req.steps_done, "evidence_photo": bool(req.evidence_photo_data_url), "note": req.note})}])
    return {"ok": True, "execution_id": eid, "recorded_at": _iso(now)}


@app.get("/trends")
def trends(node_id: str | None = None, limit: int = Query(50, ge=1, le=500), store: LocalStore = Depends(store_for)) -> list[dict[str, Any]]:
    """Aggregated style demand signal (DECISIONS §5.9). On the demo tenant this is a count of asks
    the generator and demo script planted, not a forecast -- always shown with data_label."""
    rows = store.read("style_trends")
    if node_id:
        rows = [r for r in rows if r["node_id"] == node_id]
    rows.sort(key=lambda r: (-int(r["asks"]), r["node_id"] or "", r["garment_type"] or ""))
    label = os.environ.get("TAAL_OUTCOMES_LABEL", "SYNTHETIC")
    return [{**r, "data_label": label} for r in rows[:limit]]


@app.post("/trends/recompute")
def trends_recompute(request: Request, store: LocalStore = Depends(store_for)) -> dict[str, Any]:
    """On-demand aggregation for the visitor sandbox, the same pattern as POST /measure."""
    if isinstance(store, OverlayStore):
        store._materialise("style_requests")
    tenant = load_tenant()
    vid = visitor_id(request) or "base"
    now = _now()
    rows = build_style_trends(store, _as_of(store), tenant, run_id=f"trends-{vid}", computed_at=_iso(now))
    store.write("style_trends", rows)
    return {"rows": len(rows), "window_days": int(tenant.thresholds.get("style_trends_lookback_days", 30)), "computed_at": _iso(now)}


@app.get("/sense/last")
def sense_last(store: LocalStore = Depends(store_for)) -> dict[str, Any]:
    runs = store.read("sense_runs")
    if not runs:
        raise HTTPException(404, "no sense run yet")
    return runs[-1]
