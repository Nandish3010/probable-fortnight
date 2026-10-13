"""Approve (DECISIONS §5.4): status, assignment by hash with holdout, copy, offers for treated
customers, the play as a future regressor, and the single-series re-forecast for the chart.
Idempotent: a second approve returns the recorded result with `note`."""
from __future__ import annotations

import copy as copylib
import json
import logging
import os
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from datetime import date, datetime
from typing import Any

from agents.gate.assignment import assign
from agents.gate.config import TenantConfig, load_models
from agents.gate.store import LocalStore, OverlayStore, load_catalogue
from agents.planner.context import PlannerContext
from agents.planner.tools import eligible_audience
from jobs.sense.copy import generate_copy, generate_copy_bigquery, validate_copy
from jobs.sense.copy_pregenerated import provenance_of
from jobs.sense.forecast import forecast, series_for

logger = logging.getLogger(__name__)

# Hard wall-clock budget (3 s by default; was 5 s) for the BigQuery copy branch, counted from the moment it starts (which is
# now the top of approve(), not after assignment). Past it the templated variants are used and the
# worker thread is abandoned. generate_copy_bigquery's own timeout is a per-request bound and
# job_retry can re-submit the query (see its comment), so this deadline is the real cap.
COPY_BUDGET_S = float(os.environ.get("TAAL_COPY_BUDGET_S", "3.0"))


class WindowExpired(Exception):
    """Raised when the play's window has already ended at approve time -- see `approve()`."""


def _load_play(store: LocalStore, play_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    rows = store.find("plays", play_id=play_id)
    if not rows:
        raise KeyError(play_id)
    row = rows[-1]
    return row, json.loads(row["play_json"])


def _save_play(store: LocalStore, row: dict[str, Any], play: dict[str, Any]) -> None:
    row.update({"status": play["status"], "approved_at": play.get("approved_at"), "window_start": play["window"]["start"], "window_end": play["window"]["end"], "play_json": json.dumps(play, ensure_ascii=False)})
    store.upsert("plays", "play_id", row)


def _writeoff(series: dict[str, float], on_hand: int, deadline: str, unit_cost: float) -> float:
    sold = sum(v for d, v in series.items() if d <= deadline)
    return round(max(0.0, on_hand - sold) * unit_cost, 2)


def _bigquery_copy(play: dict[str, Any], product: dict[str, Any], best_before: str | None, templated: list[dict[str, Any]], partner_name: str | None = None) -> tuple[list[dict[str, Any]], str]:
    """The templated variants, replaced slot by slot by AI.GENERATE_TABLE output (vertex backend
    only) when it returns within COPY_BUDGET_S (3.0 s, a hard wall-clock cap enforced in approve();
    generate_copy_bigquery's own timeout_s is kept just under it). Approve is on the demo's critical
    path, so any failure or timeout is absorbed here and the templated variants are returned as-is;
    this never raises. Returns (variants, "bigquery" | "templated")."""
    variants = templated
    source = "templated"
    try:
        models = load_models()
        if models["backend"] == "vertex":
            project = os.environ.get(models["vertex"]["project_env"])
            if not project:
                raise RuntimeError(f"{models['vertex']['project_env']} not set")
            bq_variants = generate_copy_bigquery(play, product, best_before, play["copy"]["language_set"], project=project, region=models["vertex"]["location"], model_id=models["ids"]["flash"], timeout_s=max(1.0, COPY_BUDGET_S - 0.2), partner_name=partner_name)
            if bq_variants:
                # Per (segment, language) slot: keep the BigQuery variant only if the same
                # deterministic validator that gates templated copy accepts it; any slot it
                # rejects, or that BigQuery didn't return at all, keeps the templated variant
                # rather than being dropped -- an offer must never go out blank.
                bq_accepted, _ = validate_copy(bq_variants, play, best_before)
                bq_by_key = {(v["segment_id"], v["language"]): v for v in bq_accepted}
                variants = [bq_by_key.get((v["segment_id"], v["language"]), v) for v in templated]
                source = "bigquery" if bq_by_key else "templated"
    except Exception as e:
        logger.warning("copy generation via BigQuery AI.GENERATE_TABLE failed, falling back to templates: %s", e)
        variants, source = templated, "templated"
    return variants, source


def _reforecast(store: LocalStore, as_of: date, run_id: str, play: dict[str, Any], stale_rows: bool) -> tuple[list[dict[str, Any]], int]:
    """Single-series re-forecast with the play as a regressor; persists the new forecast rows and
    returns (rows, latency_ms). Reads future_regressors, so it runs after they are written.
    `stale_rows` says a previous play-inclusive forecast for this SKU is already stored: only then
    does the table need a full rewrite; otherwise the new rows are appended (the same file
    content, without re-serialising the other ~130k baseline rows)."""
    t_fc = time.perf_counter()
    new_rows = forecast(store, as_of, run_id, skus=[play["target"]["sku"]], includes_plays=True)
    fc_ms = int((time.perf_counter() - t_fc) * 1000)
    if stale_rows or not (type(store) is LocalStore or isinstance(store, OverlayStore)):
        kept = [r for r in store.read("forecasts") if not (r["sku"] == play["target"]["sku"] and r.get("includes_plays"))]
        store.write("forecasts", kept + new_rows)
    else:
        store.append("forecasts", new_rows)
    return new_rows, fc_ms


def approve(store: LocalStore, tenant: TenantConfig, play_id: str, now: datetime, holdout_fraction: float | None = None, rationale: str | None = None, edits: list[dict[str, Any]] | None = None, approved_by: str = "judge", as_of: date | None = None) -> dict[str, Any]:
    row, play = _load_play(store, play_id)
    t_start = time.perf_counter()
    now_iso = now.isoformat(timespec="seconds").replace("+00:00", "Z")
    if play["status"] in ("approved", "running", "measured", "unmeasured"):
        recorded = store.find("approvals", play_id=play_id)
        if recorded:
            out = dict(recorded[-1]["response"])
            out["note"] = f"already approved at {play.get('approved_at')}; returning the recorded result"
            out["source"] = "recorded"
            return out
    gap = store.find("gaps", gap_id=play["gap_id"])[-1]
    catalogue = load_catalogue(store)
    product = catalogue[play["target"]["sku"]]
    # --- edits
    changes = list(edits or [])
    if holdout_fraction is not None and abs(holdout_fraction - play["holdout"]["fraction"]) > 1e-9:
        changes.append({"field": "holdout.fraction", "from": play["holdout"]["fraction"], "to": holdout_fraction, "at": now_iso})
        play["holdout"]["fraction"] = float(holdout_fraction)
    if rationale and rationale != play["rationale"]:
        changes.append({"field": "rationale", "from": play["rationale"], "to": rationale, "at": now_iso})
        play["rationale"] = rationale
    if changes:
        play["edits"] = (play.get("edits") or []) + changes
        play["status"] = "modified"
    # --- window starts now, unless the window already ended: this happens whenever TAAL_NOW is
    # unset and the wall clock has drifted past the seeded window, and used to silently rewrite
    # the window to [now, original_end) with original_end < now -- an inverted, empty window that
    # touches zero future_regressors rows and returns a success response with no write-off
    # movement. Fail loudly instead.
    window_end = datetime.fromisoformat(play["window"]["end"].replace("Z", "+00:00"))
    if now > window_end:
        pinned = os.environ.get("TAAL_NOW") or "<unset -- the server is using the real wall clock>"
        raise WindowExpired(f"play window ended {play['window']['end']}; the demo clock is pinned to TAAL_NOW={pinned}")
    play["window"]["start"] = now_iso
    play["status"] = "approved"
    play["approved_by"], play["approved_at"] = approved_by, now_iso
    # --- copy. A play that already carries valid copy (a recorded or seeded play with variants)
    # keeps it: no BigQuery call, source "existing". Otherwise the templated variants are computed
    # first (the immediate result and the fallback) and AI.GENERATE_TABLE in BigQuery (vertex
    # backend only) may replace them; that call runs in a worker thread concurrently with the
    # assignment, the regressor write and the re-forecast below -- see `_bigquery_copy`. It gets its
    # own snapshot of the play: this thread keeps mutating `play`. Wall time is max(copy, local
    # work), capped at COPY_BUDGET_S for the copy. Nothing else runs between here and the submit.
    partner = catalogue.get((play.get("mechanic_params") or {}).get("bundle_sku") or "")
    best_before = gap["evidence"].get("expiry_date")
    existing, existing_reasons = (validate_copy(play["copy"]["variants"], play, best_before) if play["copy"].get("variants") else ([], []))
    use_existing = bool(existing) and not existing_reasons
    pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="approve")
    t_copy = time.perf_counter()
    copy_future = None
    templated: list[dict[str, Any]] = []
    if not use_existing:
        templated = generate_copy(play, product, partner, best_before, play["copy"]["language_set"])
        copy_future = pool.submit(_bigquery_copy, copylib.deepcopy(play), product, best_before, templated, (partner or {}).get("name"))
    # --- assignment by hash
    pctx = _planner_ctx(store, tenant)
    # An assortment_gap play's real, demonstrated askers live in the gap's evidence, never the
    # grocery affinity table (agents/planner/tools.py::get_candidate_audiences has the same
    # fallback for the planner's own audience-sizing call) -- re-derive it here too, since approve
    # recomputes the audience fresh rather than trusting whatever the play declared.
    # The same filtered list the gate sized the play from (agents/planner/tools.py::eligible_audience),
    # so treated + holdout always equals the play's audience.size_after_consent.
    ids, eligible = eligible_audience(pctx, play)
    subscribers = {c["customer_id"] for c in store.read("customers") if play["target"]["sku"] in (c.get("subscription_skus") or [])}
    rows = assign(play, eligible, assigned_at=now_iso)
    for r in rows:
        r["tenant_id"] = tenant.tenant_id
    store.append("play_assignments", rows)
    treated = [r["customer_id"] for r in rows if r["arm"] == "treated"]
    holdout = [r["customer_id"] for r in rows if r["arm"] == "holdout"]
    # --- the play becomes a known future regressor. This must land before the re-forecast reads
    # future_regressors, and it needs only the window, so it runs ahead of the concurrent branches.
    nodes = {n["node_id"]: n for n in store.read("nodes")}
    clusters = {nodes[n]["cluster_id"] for n in play["target"]["node_ids"] if n in nodes}
    w0, w1 = date.fromisoformat(play["window"]["start"][:10]), date.fromisoformat(play["window"]["end"][:10])
    regs = store.read("future_regressors")
    touched = 0
    for r in regs:
        if r["sku"] == play["target"]["sku"] and r["cluster_id"] in clusters and w0.isoformat() <= r["date"] <= w1.isoformat():
            r["on_promo"], r["play_id"] = True, play_id
            touched += 1
    store.write("future_regressors", regs)
    # --- the single-series re-forecast runs in the second worker while this thread finishes its own
    # reads; offers below need the assignment and the copy, so they wait for the join. The copy
    # branch absorbs every error into the templated variants and so cannot fail; a forecast error
    # is re-raised only after the copy branch has finished or timed out, so neither cancels the other.
    as_of = as_of or date.fromisoformat(gap["created_at"])
    sku = play["target"]["sku"]
    # one pass over the forecasts file for this SKU's rows (baseline for the chart, and whether a
    # play-inclusive forecast already exists), instead of parsing the whole table twice
    sku_rows = store.read_where("forecasts", "sku", [sku])
    baseline_rows = [r for r in sku_rows if not r.get("includes_plays")]
    stale_rows = len(baseline_rows) != len(sku_rows)
    run_id = f"refc_{play_id}_{now.strftime('%H%M%S')}"
    forecast_future = pool.submit(_reforecast, store, as_of, run_id, play, stale_rows)
    forecast_error = forecast_future.exception()
    copy_provenance = None
    if use_existing:
        variants, copy_source = existing, "existing"
        # "bigquery_pregenerated" only when the stored variants are exactly the committed
        # AI.GENERATE_TABLE output for this play (jobs/sense/copy_pregenerated.py); otherwise the
        # provenance is just the source ("existing": a recorded or seeded play that carried copy).
        copy_provenance = provenance_of(play, best_before, existing)
    else:
        try:
            variants, copy_source = copy_future.result(timeout=max(0.0, COPY_BUDGET_S - (time.perf_counter() - t_copy)))
        except FutureTimeout:
            logger.warning("copy generation via BigQuery passed its %.1f s budget, using the templated variants", COPY_BUDGET_S)
            variants, copy_source = templated, "templated"
    pool.shutdown(wait=False, cancel_futures=True)
    if forecast_error is not None:
        raise forecast_error
    new_rows, fc_ms = forecast_future.result()
    accepted, reasons = validate_copy(variants, play, best_before)
    play["copy"]["variants"] = accepted
    play["copy"]["copy_status"] = "validated" if accepted and not reasons else ("rejected" if not accepted else "validated")
    # --- offers for treated only
    lang_of = {c["customer_id"]: c.get("language", "en") for c in store.read("customers")}
    text_by_lang = {v["language"]: v["text"] for v in accepted}
    offers = []
    for cid in treated:
        text = text_by_lang.get(lang_of.get(cid, "en")) or text_by_lang.get("en") or (accepted[0]["text"] if accepted else "")
        offers.append({"offer_id": f"{play_id}|{cid}", "tenant_id": tenant.tenant_id, "customer_id": cid, "play_id": play_id, "sku": play["target"]["sku"], "mechanic": play["mechanic"], "mechanic_params": play.get("mechanic_params") or {}, "text": text, "best_before_date": best_before, "created_at": now_iso, "delivered_at": None, "redeemed_at": None})
    if offers:
        store.append("offers", offers)
    base_series = series_for(baseline_rows, play["target"]["sku"], play["target"]["node_ids"])
    play_series = series_for(new_rows, play["target"]["sku"], play["target"]["node_ids"])
    p10 = defaultdict(float)
    p90 = defaultdict(float)
    for r in new_rows:
        if r["node_id"] in play["target"]["node_ids"]:
            p10[r["date"]] += r["p10"]
            p90[r["date"]] += r["p90"]
    on_hand = int(gap["evidence"].get("on_hand") or play["target"]["units"])
    unit_cost = float(product["unit_cost"])
    deadline = play["target"]["deadline_date"]
    series = [{"date": d, "baseline_p50": round(base_series.get(d, 0.0), 2), "play_p50": round(play_series.get(d, 0.0), 2), "p10": round(p10.get(d, 0.0), 2), "p90": round(p90.get(d, 0.0), 2)} for d in sorted(set(base_series) | set(play_series))]
    resp = {
        "play_id": play_id, "status": play["status"],
        "assignment": {"treated_n": len(treated), "holdout_n": len(holdout), "seed": play["holdout"]["seed"], "fraction": play["holdout"]["fraction"], "eligible_n": len(eligible), "excluded_subscribers": len([c for c in ids if c in subscribers]) if play["mechanic"] in ("coupon", "outlet_markdown", "bundle") else 0},
        "offers_written": len(offers), "regressor_rows_touched": touched, "copy": {"variants": len(accepted), "rejected": reasons, "source": copy_source, "provenance": copy_provenance or copy_source},
        # The model that actually ran: jobs/sense/forecast.py's local seasonal-xreg forecaster,
        # not the BigQuery ML.FORECAST/ARIMA_PLUS_XREG function -- that function was verified
        # separately against real BigQuery (eval/raw/bigquery_arima_xreg_forecast_2026-09-23.json)
        # but is not wired into this re-forecast path. Name only what ran here.
        "forecast": {"run_id": run_id, "model": new_rows[0]["model"] if new_rows else "local_seasonal_xreg", "latency_ms": fc_ms, "series": series, "writeoff_before_inr": _writeoff(base_series, on_hand, deadline, unit_cost), "writeoff_after_inr": _writeoff(play_series, on_hand, deadline, unit_cost), "play_window": play["window"]},
        "source": "live", "elapsed_ms": int((time.perf_counter() - t_start) * 1000),
    }
    _save_play(store, row, play)
    store.append("approvals", [{"play_id": play_id, "at": now_iso, "response": resp}])
    store.append_event(f"approve_{play_id}", {"seq": 0, "run_id": f"approve_{play_id}", "invocation_id": "", "author": "approve", "timestamp": now.timestamp(), "ts_offset_ms": 0, "text": f"approved by {approved_by}; treated {len(treated)}, holdout {len(holdout)}; re-forecast {run_id} in {fc_ms} ms", "level": "ok"})
    return resp


def _planner_ctx(store: LocalStore, tenant: TenantConfig) -> PlannerContext:
    ctx = PlannerContext.__new__(PlannerContext)
    mp = store.root / "manifest.json"
    if not mp.exists() and hasattr(store, "base"):
        mp = store.base.root / "manifest.json"
    ctx.store, ctx.tenant, ctx.run_id = store, tenant, "approve"
    ctx.as_of = date.fromisoformat(json.loads(mp.read_text(encoding="utf-8"))["as_of"]) if mp.exists() else date.today()
    ctx.policy_text, ctx.policy_version = tenant.policy_text, tenant.policy_version
    ctx.products = load_catalogue(store)
    ctx.nodes = {n["node_id"]: n for n in store.read("nodes")}
    return ctx

