#!/usr/bin/env python3
"""Docs truth sweep (2026-09-27), Task 2: the README hook (gap_chips_ds07 / play_chips_ds07_v1).

Unlike impact_numbers.py, this script is NOT limited to committed files: it executes the repo's
real code (data.generator / jobs.sense / harness.seed_plays must already have been run into the
scratch tenant dir below -- see commands.txt) and calls services.api.approve.approve(...) for
real, exactly the way services/api/main.py's POST /approve route does, against that scratch
store. It writes/mutates ONLY the scratch tenant dir, never .local/.

Preconditions (see commands.txt for the exact commands run before this script):
    export TAAL_MODEL_BACKEND=stub
    export TAAL_TENANT_CONFIG=config/tenant.demo.toml
    export TAAL_NOW=2026-09-12T03:30:00Z
    export TAAL_DATA_DIR=<scratch dir>
    uv run python -m data.generator --out "$TAAL_DATA_DIR" --seed 20260912
    uv run python -m jobs.sense
    uv run python -m harness.seed_plays

Run (from repo root, same env still exported):
    uv run python eval/raw/docs_truth_sweep_2026-09-27/hook_numbers.py

Writes hook_numbers.json next to this script and prints it to stdout.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import UTC, date, datetime
from pathlib import Path

THIS_FILE = Path(__file__).resolve()
REPO_ROOT = THIS_FILE.parents[3]
OUT_PATH = THIS_FILE.with_name("hook_numbers.json")

DEFAULT_SCRATCH = "/tmp/sandbox-scratch/sweep_tenant"

# --------------------------------------------------------------------------------------- env / preconditions

env_report = {}
for key, default in (
    ("TAAL_MODEL_BACKEND", "stub"),
    ("TAAL_TENANT_CONFIG", "config/tenant.demo.toml"),
    ("TAAL_NOW", "2026-09-12T03:30:00Z"),
    ("TAAL_DATA_DIR", DEFAULT_SCRATCH),
):
    val = os.environ.get(key)
    env_report[key] = {"value": val, "was_set_by_caller": val is not None, "expected": default}
    os.environ.setdefault(key, default)

if os.environ["TAAL_DATA_DIR"] in (".local/data", str(REPO_ROOT / ".local/data")):
    raise SystemExit("refusing to run: TAAL_DATA_DIR points at .local/data, not the scratch dir")

SCRATCH_DIR = Path(os.environ["TAAL_DATA_DIR"])
if not (SCRATCH_DIR / "manifest.json").exists():
    raise SystemExit(
        f"scratch tenant not found at {SCRATCH_DIR} -- run data.generator / jobs.sense / "
        "harness.seed_plays into it first (see commands.txt)"
    )

sys.path.insert(0, str(REPO_ROOT))
from agents.gate.config import load_tenant  # noqa: E402
from agents.gate.store import LocalStore  # noqa: E402
from services.api.approve import approve as do_approve  # noqa: E402

store = LocalStore(SCRATCH_DIR)
manifest = json.loads((store.root / "manifest.json").read_text(encoding="utf-8"))
env_report["scratch_dir_really_used"] = {
    "store.root": str(store.root),
    "matches_TAAL_DATA_DIR": str(store.root) == str(SCRATCH_DIR),
    "manifest_seed": manifest.get("seed"),
    "manifest_as_of": manifest.get("as_of"),
    "manifest_sha256_present_for_n_tables": len(manifest.get("sha256", {})),
}

PINNED_DATE = date.fromisoformat(os.environ["TAAL_NOW"][:10])  # 2026-09-12

# --------------------------------------------------------------------------------------- gap_chips_ds07

gaps = store.read("gaps")
gap = next(g for g in gaps if g["gap_id"] == "gap_chips_ds07")

products = {p["sku"]: p for p in store.read("products")}
product = products[gap["sku"]]

batches = store.read("inventory_batches")
batch = next(b for b in batches if b["batch_id"] == gap["batch_id"])

expiry_date = date.fromisoformat(batch["expiry_date"])
sellby_date = date.fromisoformat(batch["online_sellby_date"])
days_to_expiry = (expiry_date - PINNED_DATE).days
days_to_sellby = (sellby_date - PINNED_DATE).days

gap_facts = {
    "gap_id": gap["gap_id"],
    "type": gap["type"],
    "sku": gap["sku"],
    "sku_name": product["name"],
    "node_id": gap["node_id"],
    "batch_id": gap["batch_id"],
    "units_at_risk": gap["units_at_risk"],
    "rupees_at_stake": gap["rupees_at_stake"],
    "deadline_date": gap["deadline_date"],
    "deadline_type": gap["deadline_type"],
    "sellby_rule_version": gap["evidence"]["sellby_rule"],
    "shelf_life_days": product["shelf_life_days"],
    "batch_expiry_date": batch["expiry_date"],
    "batch_online_sellby_date": batch["online_sellby_date"],
    "batch_received_at": batch["received_at"],
    "pinned_date": PINNED_DATE.isoformat(),
    "days_pinned_to_expiry": days_to_expiry,
    "days_pinned_to_sellby": days_to_sellby,
    "source": {
        "gap": "gaps.jsonl (scratch tenant, seeded) find gap_id=gap_chips_ds07",
        "product": "products.jsonl (scratch tenant, seeded) find sku=" + gap["sku"],
        "batch": "inventory_batches.jsonl (scratch tenant, seeded) find batch_id=" + gap["batch_id"],
    },
}

# sell-by rule cross-check (config/tenant.demo.toml [sellby_rule], v1-either: online sell-by =
# expiry - min(min_fraction_remaining * shelf_life_days, min_days_remaining))
import tomllib  # noqa: E402

tenant_toml = tomllib.loads((REPO_ROOT / "config/tenant.demo.toml").read_text(encoding="utf-8"))
sbr = tenant_toml["sellby_rule"]
computed_cutoff_days = min(sbr["min_fraction_remaining"] * product["shelf_life_days"], sbr["min_days_remaining"])
from datetime import timedelta  # noqa: E402

computed_sellby_date = expiry_date - timedelta(days=round(computed_cutoff_days))
gap_facts["sellby_rule_check"] = {
    "rule_version_in_toml": sbr["version"],
    "rule_version_on_gap": gap["evidence"]["sellby_rule"],
    "min_fraction_remaining": sbr["min_fraction_remaining"],
    "min_days_remaining": sbr["min_days_remaining"],
    "combine": sbr["combine"],
    "computed_cutoff_days_before_expiry": round(computed_cutoff_days, 2),
    "computed_online_sellby_date": computed_sellby_date.isoformat(),
    "matches_batch_online_sellby_date": computed_sellby_date.isoformat() == batch["online_sellby_date"],
    "source": "config/tenant.demo.toml [sellby_rule]",
}

# --------------------------------------------------------------------------------------- planner event trace

play_rows = store.find("plays", play_id="play_chips_ds07_v1")
assert play_rows, "play_chips_ds07_v1 not found -- did harness.seed_plays run into this scratch dir?"
play_row = play_rows[-1]
play = json.loads(play_row["play_json"])
trace_ref = play["trace_ref"]  # e.g. "events/run_chips_ds07_v1_bd0a8253"
run_id = trace_ref.rsplit("/", 1)[-1]
events = store.read_events(run_id)

propose_calls = [e for e in events if (e.get("function_call") or {}).get("name") == "propose_play"]
propose_responses = [e for e in events if (e.get("function_response") or {}).get("name") == "propose_play"]
warn_texts = [e for e in events if e.get("level") == "warn"]

assert len(propose_calls) >= 2, f"expected at least 2 propose_play drafts (a first draft + a revision), found {len(propose_calls)}"

first_call = propose_calls[0]["function_call"]["args"]["play"]
first_response = propose_responses[0]["function_response"]["response"]
final_call = propose_calls[-1]["function_call"]["args"]["play"]
final_response = propose_responses[-1]["function_response"]["response"]
revision_warn = next((e for e in warn_texts if "Revising the play" in (e.get("text") or "")), None)

planner_trace = {
    "trace_file": f"events/{run_id}.jsonl (scratch tenant, seeded by harness.seed_plays)",
    "n_events": len(events),
    "n_propose_play_drafts": len(propose_calls),
    "first_draft": {
        "seq": propose_calls[0]["seq"],
        "mechanic": first_call["mechanic"],
        "mechanic_params": first_call["mechanic_params"],
    },
    "first_draft_guardrail_failure": {
        "seq": propose_responses[0]["seq"],
        "valid": first_response.get("valid"),
        "errors": first_response.get("errors"),
    },
    "revision_log_line": {
        "seq": revision_warn["seq"] if revision_warn else None,
        "text": revision_warn.get("text") if revision_warn else None,
    },
    "final_draft": {
        "seq": propose_calls[-1]["seq"],
        "mechanic": final_call["mechanic"],
        "mechanic_params": final_call["mechanic_params"],
        "alternatives_recorded": final_call.get("alternatives"),
    },
    "final_validation": {
        "seq": propose_responses[-1]["seq"],
        "valid": final_response.get("valid"),
        "play_id": final_response.get("play_id"),
    },
    "seed_plays_stdout_iterations": "seed: gap_chips_ds07 -> proposed play_chips_ds07_v1 (2 iteration(s))  # from commands.txt run log",
}

# --------------------------------------------------------------------------------------- approve(), mirroring services/api/main.py's POST /approve route
#
#   services/api/main.py:346-348 -- @app.post("/approve") approve_play():
#     return do_approve(store, load_tenant(), req.play_id, _now(), req.holdout_fraction,
#                        req.rationale, req.edits, req.approved_by or "judge", as_of=_as_of(store))
#   For a bare "Approve" click (judge mode, no manual edits): holdout_fraction=None,
#   rationale=None, edits=None, approved_by defaults server-side to "judge".
#   _now() = TAAL_NOW when pinned (main.py:52-61). _as_of(store) = store's manifest.json as_of
#   (main.py:72-76), which for this scratch tenant is 2026-09-12 (matches TAAL_NOW's date).

tenant = load_tenant()
now = datetime.fromisoformat(os.environ["TAAL_NOW"].replace("Z", "+00:00")).astimezone(UTC)
as_of = date.fromisoformat(manifest["as_of"])

assert play["status"] == "proposed", (
    f"expected play_chips_ds07_v1 status 'proposed' before this script's approve() call, found "
    f"{play['status']!r} -- scratch tenant may already have been approved by a previous run of "
    "this script; re-generate the scratch tenant for a clean measurement"
)

resp = do_approve(store, tenant, "play_chips_ds07_v1", now, None, None, None, "judge", as_of=as_of)

approve_result = {
    "called_as": 'do_approve(store, tenant, "play_chips_ds07_v1", now, None, None, None, "judge", as_of=as_of)',
    "now": now.isoformat(),
    "as_of": as_of.isoformat(),
    "response_source": resp["source"],
    "assignment": resp["assignment"],
    "offers_written": resp["offers_written"],
    "regressor_rows_touched": resp["regressor_rows_touched"],
    "copy": resp["copy"],
    "forecast": {
        "run_id": resp["forecast"]["run_id"],
        "model": resp["forecast"]["model"],
        "latency_ms": resp["forecast"]["latency_ms"],
        "writeoff_before_inr": resp["forecast"]["writeoff_before_inr"],
        "writeoff_after_inr": resp["forecast"]["writeoff_after_inr"],
        "n_series_points": len(resp["forecast"]["series"]),
    },
    "elapsed_ms_total_approve_call": resp["elapsed_ms"],
}

# --------------------------------------------------------------------------------------- search committed eval/raw/ for a deployed/live latency figure

import re  # noqa: E402

EVAL_RAW = REPO_ROOT / "eval/raw"
live_latency_hits = []
for p in sorted(EVAL_RAW.rglob("*")):
    if not p.is_file() or p.is_relative_to(THIS_FILE.parent):
        continue
    if p.suffix.lower() not in (".txt", ".json", ".md"):
        continue
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except Exception:
        continue
    for i, line in enumerate(text.splitlines(), start=1):
        if re.search(r"POST /approve\b", line) or ("refc_" in line):
            live_latency_hits.append({"file": str(p.relative_to(REPO_ROOT)), "line": i, "text": line.strip()})

# --------------------------------------------------------------------------------------- README claims check

def _close(actual: float, target: float, rel_tol: float) -> bool:
    return abs(actual - target) <= rel_tol * target

readme_claims_check = [
    {
        "claim": "a 90-day-shelf-life chips pack expiring in 33 days can be sold online for 6 more days",
        "reproduced": {
            "shelf_life_days": product["shelf_life_days"],
            "days_pinned_to_expiry": days_to_expiry,
            "days_pinned_to_sellby": days_to_sellby,
        },
        "match": product["shelf_life_days"] == 90 and days_to_expiry == 33 and days_to_sellby == 6,
    },
    {
        "claim": "demo gap gap_chips_ds07 is 368 units of Masala Chips at DS-07 with Rs 9,200 at stake and online sell-by in 6 days",
        "reproduced": {
            "units_at_risk": gap["units_at_risk"],
            "sku_name": product["name"],
            "node_id": gap["node_id"],
            "rupees_at_stake": gap["rupees_at_stake"],
            "days_pinned_to_sellby": days_to_sellby,
        },
        "match": (
            gap["units_at_risk"] == 368
            and "Masala Chips" in product["name"]
            and gap["node_id"] == "DS-07"
            and gap["rupees_at_stake"] == 9200.0
            and days_to_sellby == 6
        ),
    },
    {
        "claim": "the planner's first draft (a 15% coupon) fails the margin floor and it revises to a bundle",
        "reproduced": {
            "first_draft_mechanic": first_call["mechanic"],
            "first_draft_discount_pct": first_call["mechanic_params"].get("discount_pct"),
            "guardrail_errors": first_response.get("errors"),
            "final_mechanic": final_call["mechanic"],
        },
        "match": (
            first_call["mechanic"] == "coupon"
            and first_call["mechanic_params"].get("discount_pct") == 15
            and any("margin_floor" in e for e in (first_response.get("errors") or []))
            and final_call["mechanic"] == "bundle"
        ),
    },
    {
        "claim": "approval assigns 287 treated and 26 holdout customers by hash",
        "reproduced": {
            "treated_n": resp["assignment"]["treated_n"],
            "holdout_n": resp["assignment"]["holdout_n"],
        },
        "match": resp["assignment"]["treated_n"] == 287 and resp["assignment"]["holdout_n"] == 26,
    },
    {
        "claim": "approval ... re-forecasts the series in about 1.5 s",
        "reproduced": {"forecast_latency_ms": resp["forecast"]["latency_ms"]},
        "match": _close(resp["forecast"]["latency_ms"], 1500, 0.5),
        "match_rule": "within +/-50% of 1500ms (1500ms is 'about 1.5s' in prose, not an exact spec)",
    },
]

# --------------------------------------------------------------------------------------- explicit {value, unit, label, source, note} per figure
#
# Labels follow the task's own rule: tenant quantities (gap/product/batch facts, planner trace,
# assignment/regressor/copy counts, the pre-play baseline writeoff) = "seeded" (deterministic
# output of data.generator/jobs.sense/harness.seed_plays + approve()'s deterministic hash
# assignment and its deterministic local forecaster, TAAL_MODEL_BACKEND=stub, no LLM); wall-clock
# timings from this run = "measured" (real, one run, this sandbox); the post-approve re-forecast
# total (which bakes in the play's assumed promo effect) = "projected".

GAP_SRC = "gaps.jsonl (scratch tenant, seeded)"
PROD_SRC = "products.jsonl (scratch tenant, seeded)"
BATCH_SRC = "inventory_batches.jsonl (scratch tenant, seeded)"
TRACE_SRC = f"events/{run_id}.jsonl (scratch tenant, seeded by harness.seed_plays)"
APPROVE_SRC = 'services.api.approve.approve(store, tenant, "play_chips_ds07_v1", now, None, None, None, "judge", as_of=as_of) response (this run)'

labeled_values = {
    "units_at_risk": {"value": gap["units_at_risk"], "unit": "units", "label": "seeded", "source": f"{GAP_SRC} gap_chips_ds07.units_at_risk", "note": None},
    "rupees_at_stake": {"value": gap["rupees_at_stake"], "unit": "INR", "label": "seeded", "source": f"{GAP_SRC} gap_chips_ds07.rupees_at_stake", "note": None},
    "shelf_life_days": {"value": product["shelf_life_days"], "unit": "days", "label": "seeded", "source": f"{PROD_SRC} products[sku={gap['sku']}].shelf_life_days", "note": None},
    "days_pinned_to_expiry": {"value": days_to_expiry, "unit": "days", "label": "seeded", "source": f"{BATCH_SRC} batch.expiry_date ({batch['expiry_date']}) minus pinned TAAL_NOW date ({PINNED_DATE.isoformat()})", "note": "arithmetic on seeded dates, computed in this script"},
    "days_pinned_to_sellby": {"value": days_to_sellby, "unit": "days", "label": "seeded", "source": f"{BATCH_SRC} batch.online_sellby_date ({batch['online_sellby_date']}) minus pinned TAAL_NOW date ({PINNED_DATE.isoformat()})", "note": "cross-checked against config/tenant.demo.toml [sellby_rule] recomputation, see gap_chips_ds07.sellby_rule_check"},
    "first_draft_mechanic": {"value": first_call["mechanic"], "unit": "mechanic name", "label": "seeded", "source": f"{TRACE_SRC} seq={propose_calls[0]['seq']} function_call.args.play.mechanic", "note": None},
    "first_draft_discount_pct": {"value": first_call["mechanic_params"].get("discount_pct"), "unit": "percent", "label": "seeded", "source": f"{TRACE_SRC} seq={propose_calls[0]['seq']} function_call.args.play.mechanic_params.discount_pct", "note": None},
    "guardrail_failed": {"value": (first_response.get("errors") or [None])[0], "unit": "text", "label": "seeded", "source": f"{TRACE_SRC} seq={propose_responses[0]['seq']} function_response.response.errors[0]", "note": None},
    "revision_mechanic": {"value": final_call["mechanic"], "unit": "mechanic name", "label": "seeded", "source": f"{TRACE_SRC} seq={propose_calls[-1]['seq']} function_call.args.play.mechanic", "note": None},
    "treated_n": {"value": resp["assignment"]["treated_n"], "unit": "customers", "label": "seeded", "source": APPROVE_SRC + ".assignment.treated_n", "note": "assignment is a deterministic hash of customer_id + play.holdout.seed (agents/gate/assignment.py), independent of model backend"},
    "holdout_n": {"value": resp["assignment"]["holdout_n"], "unit": "customers", "label": "seeded", "source": APPROVE_SRC + ".assignment.holdout_n", "note": "matches holdout_n=26 in the live-Vertex sweeps too (eval/raw/sweep_vertex_2026-09-20.txt, sweep_vertex_2026-09-21.txt), i.e. backend-independent"},
    "eligible_n": {"value": resp["assignment"]["eligible_n"], "unit": "customers", "label": "seeded", "source": APPROVE_SRC + ".assignment.eligible_n", "note": None},
    "regressor_rows_touched": {"value": resp["regressor_rows_touched"], "unit": "future_regressors rows", "label": "seeded", "source": APPROVE_SRC + ".regressor_rows_touched", "note": None},
    "forecast_model": {"value": resp["forecast"]["model"], "unit": "model name", "label": "seeded", "source": APPROVE_SRC + ".forecast.model", "note": "jobs/sense/forecast.py's local seasonal-xreg forecaster; not BigQuery ML.FORECAST/ARIMA_PLUS_XREG (services/api/approve.py's own comment)"},
    "forecast_latency_ms": {"value": resp["forecast"]["latency_ms"], "unit": "milliseconds", "label": "measured", "source": APPROVE_SRC + ".forecast.latency_ms", "note": "real wall-clock on this sandbox, one run, local stub-backend forecast() call only -- no live Gemini/BigQuery call is on this path even with TAAL_MODEL_BACKEND=vertex (see deployed_or_live_latency_search for the separate, larger, live end-to-end /approve latency)"},
    "elapsed_ms_total_approve_call": {"value": resp["elapsed_ms"], "unit": "milliseconds", "label": "measured", "source": APPROVE_SRC + ".elapsed_ms", "note": "real wall-clock for the whole approve() call on this sandbox, one run, stub backend (no live copy-generation call)"},
    "writeoff_before_inr": {"value": resp["forecast"]["writeoff_before_inr"], "unit": "INR", "label": "seeded", "source": APPROVE_SRC + ".forecast.writeoff_before_inr", "note": "baseline (pre-play) forecast's write-off, from the same deterministic local forecaster over seeded sales history; exactly matches 9194.12 in both eval/raw/sweep_vertex_2026-09-20.txt and _21.txt (same gap, same play, live Vertex backend, different day) -- backend-independent"},
    "writeoff_after_inr": {"value": resp["forecast"]["writeoff_after_inr"], "unit": "INR", "label": "projected", "source": APPROVE_SRC + ".forecast.writeoff_after_inr", "note": "re-forecast WITH the play's on_promo regressor set -- bakes in the estimator/forecaster's assumed response to the play, not an observed sale; exactly matches eval/raw/sweep_vertex_2026-09-21.txt's 8067.53"},
}

# --------------------------------------------------------------------------------------- assemble + write

result = {
    "_meta": {
        "generated_by": "eval/raw/docs_truth_sweep_2026-09-27/hook_numbers.py",
        "env": env_report,
        "note": (
            "Tenant quantities (gap/product/batch facts, planner trace, treated_n/holdout_n/"
            "eligible_n/regressor_rows_touched) are labelled 'seeded': deterministic output of "
            "data.generator --seed 20260912 + jobs.sense + harness.seed_plays, TAAL_MODEL_BACKEND="
            "stub (no LLM calls) against the scratch tenant. forecast.latency_ms and the total "
            "approve() elapsed_ms are labelled 'measured': a real wall-clock measurement on this "
            "sandbox, one run, local stub-backend forecaster (jobs/sense/forecast.py's "
            "local_seasonal_xreg), not the BigQuery ML.FORECAST/ARIMA_PLUS_XREG path and not "
            "necessarily representative of a loaded/deployed Cloud Run instance's latency. "
            "writeoff_after_inr is labelled 'projected': it depends on the just-approved play's "
            "on_promo regressor changing the re-forecast, which is itself a model output, not a "
            "measured sale."
        ),
    },
    "labeled_values": labeled_values,
    "gap_chips_ds07": gap_facts,
    "planner_trace": planner_trace,
    "approve_call": approve_result,
    "deployed_or_live_latency_search": {
        "searched": "eval/raw/**/*.{txt,json,md} for 'POST /approve' or 'refc_' lines (excluding this task's own output dir)",
        "hits": live_latency_hits,
        "note": (
            "Two real hits: eval/raw/sweep_vertex_2026-09-20.txt and eval/raw/sweep_vertex_2026-09-21.txt, "
            "both harness.sweep_live runs against play_chips_ds07_v1 itself (same gap/play as this "
            "hook) on a live TAAL_MODEL_BACKEND=vertex server (GET /health backend=vertex; real "
            "Gemini + BigQuery AI.GENERATE_TABLE copy calls happen inside that /approve). Total "
            "POST /approve endpoint latency there was 12.3s (2026-09-20) and 8.3s (2026-09-21) -- "
            "NOT the same measurement as forecast.latency_ms above: that total includes the live "
            "copy-generation call (services/api/approve.py's generate_copy_bigquery, ~3-4s "
            "measured elsewhere per docs/scale.md, 6s timeout) on top of assignment + re-forecast. "
            "harness/sweep_live.py defaults to http://localhost:8080 and also accepts a "
            "*.run.app Cloud Run URL as argv[1]; neither of these two committed log files records "
            "which base URL that run actually used, so whether this was the deployed Cloud Run "
            "service specifically or a local server running with real Vertex credentials could "
            "NOT be confirmed from the committed file alone. holdout_n=26 in both live runs, "
            "matching this script's own approve_call.assignment.holdout_n below."
        ),
    },
    "readme_claims_check": readme_claims_check,
}

OUT_PATH.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(json.dumps(result, indent=2, ensure_ascii=False))
