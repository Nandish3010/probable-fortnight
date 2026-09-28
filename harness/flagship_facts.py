"""Recompute every number the README hook ("Demo gap `gap_chips_ds07`: ...") states, from a
freshly seeded demo tenant, each tagged with a label (seeded / measured / configured) and where
it came from -- so the paragraph can be re-verified rather than trusted.

    make generate
    uv run python -m harness.flagship_facts [--out eval/raw/flagship_facts_2026-09-27.json]

Reads TAAL_DATA_DIR (default `.local/data`, the `make generate` output) and requires
TAAL_MODEL_BACKEND=stub: this script describes the fixture judges actually see in this build
environment (the scripted stub -- no cloud credential exists here to record a real Gemini run;
see harness/record_flagship_traces.py). It refuses to run under any other backend rather than
silently describing something else as "the seeded flagship play".

Five things land in the output, each under its own key:
  - `gap`: the gap_chips_ds07 row (units_at_risk, rupees_at_stake, deadline_date, deadline_type),
    the tenant's `as_of`, the days between them, and the product's shelf_life_days -- all seeded
    by data.generator/jobs.sense, read back, never typed by hand.
  - `flagship_play`: the seeded play's source/mechanic/mechanic_params, and every propose_play
    attempt recorded in its trace, in order (mechanic, mechanic_params, valid, the rule ids of any
    guardrail that failed it).
  - `approve`: one real POST /approve through FastAPI's TestClient, against a throwaway visitor
    sandbox that touches no file under version control -- the assignment split and the writeoff
    the chart would show, plus the forecaster's own measured wall time (a local process call, not
    the deployed service).
  - `configured_replan_deadline_s`: TAAL_PLANNER_DEADLINE_S parsed out of infra/deploy.sh's real
    `taal-agents` deploy command, not copied from prose.
  - `planner_prompt_v6`: the min/max elapsed_ms of the after-prompt-v6 runs that actually reached
    the model, from the committed real-Vertex session summary of 2026-09-24 -- the last real
    Gemini latency this project has on file for this planner.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from agents.gate.config import ROOT, load_models
from agents.gate.store import LocalStore
from agents.planner import tools as pt
from agents.planner.context import PlannerContext, reset_context, set_context

GAP_ID = "gap_chips_ds07"
VISITOR_ID = "factsprobe01"
DEPLOY_SH = ROOT / "infra" / "deploy.sh"
V6_SUMMARY = ROOT / "eval" / "raw" / "planner_prompt_v6_2026-09-24" / "summary.json"
DEFAULT_OUT = ROOT / "eval" / "raw" / "flagship_facts_2026-09-27.json"


class FactsAbort(Exception):
    """A clear, expected refusal (wrong backend, nothing seeded yet, a malformed trace) -- caught
    once in main() and printed as one line, not a traceback."""


def _val(value: Any, label: str, source: str) -> dict[str, Any]:
    return {"value": value, "label": label, "source": source}


def _guardrail_rule_ids(errors: list[str]) -> list[str]:
    """The same `guardrail <rule_id>: <detail>` parse harness/record_flagship_traces.py's
    `_rejection` uses, kept local here since this script never runs a planner and has no other
    reason to import that recorder module."""
    return [m.group(1) for e in errors for m in [re.match(r"^guardrail (\S+):", e)] if m]


# ------------------------------------------------------------------------------------- gap facts

def _gap_facts(data_dir: Path) -> dict[str, Any]:
    manifest_path = data_dir / "manifest.json"
    if not manifest_path.exists():
        raise FactsAbort(f"{manifest_path} does not exist -- run `make generate` first")
    as_of = json.loads(manifest_path.read_text(encoding="utf-8"))["as_of"]

    ctx = PlannerContext.build(data_dir, run_id="flagship-facts-gap")
    token = set_context(ctx)
    try:
        try:
            gap = pt.get_gap(GAP_ID)
        except KeyError as e:
            raise FactsAbort(f"unknown gap {e} -- run `make generate` first") from e
    finally:
        reset_context(token)

    days = (date.fromisoformat(gap["deadline_date"]) - date.fromisoformat(as_of)).days
    src = "gaps.jsonl (data.generator -> jobs.sense), read via agents.planner.tools.get_gap"
    return {
        "as_of": _val(as_of, "seeded", "manifest.json"),
        "units_at_risk": _val(gap["units_at_risk"], "seeded", src),
        "rupees_at_stake": _val(gap["rupees_at_stake"], "seeded", src),
        "deadline_date": _val(gap["deadline_date"], "seeded", src),
        "deadline_type": _val(gap["deadline_type"], "seeded", src),
        "days_as_of_to_deadline": _val(days, "computed", "deadline_date minus as_of, both above"),
        "product_name": gap["product"]["name"],
        "product_shelf_life_days": _val(gap["product"]["shelf_life_days"], "seeded", "data/generator/catalog.py, read via agents.planner.tools.get_gap"),
    }


# --------------------------------------------------------------------------------- play + trace

def _propose_play_attempts(trace: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Every propose_play call/response pair in `trace`, in order. Calls and responses are
    collected separately (filtered to name == "propose_play") and zipped rather than matched by
    adjacency, since other tool calls (estimate_outcomes, check_guardrails) can appear in between
    without breaking the 1:1 call/response order a single-threaded tool-calling loop guarantees."""
    calls = [rec["function_call"]["args"]["play"] for rec in trace if (rec.get("function_call") or {}).get("name") == "propose_play"]
    resps = [rec["function_response"]["response"] for rec in trace if (rec.get("function_response") or {}).get("name") == "propose_play"]
    if len(calls) != len(resps):
        raise FactsAbort(f"flagship trace has {len(calls)} propose_play call(s) but {len(resps)} response(s) -- malformed trace, refusing to guess a pairing")
    if not calls:
        raise FactsAbort("flagship trace has no propose_play call at all")
    attempts = []
    for i, (call, resp) in enumerate(zip(calls, resps, strict=True), start=1):
        attempts.append({
            "attempt": i,
            "mechanic": call.get("mechanic"),
            "mechanic_params": call.get("mechanic_params"),
            "valid": bool(resp.get("valid")),
            "failing_guardrail_rule_ids": _guardrail_rule_ids(resp.get("errors") or []),
        })
    return attempts


def _flagship_play_facts(data_dir: Path) -> dict[str, Any]:
    store = LocalStore(data_dir)
    rows = store.find("plays", gap_id=GAP_ID)
    if not rows:
        raise FactsAbort(f"no play seeded for {GAP_ID} in {data_dir} -- run `make generate` first")
    play = json.loads(rows[-1]["play_json"])
    source = play.get("source")
    if source != "scripted_stub":
        raise FactsAbort(
            f"expected the seeded flagship play's source to be 'scripted_stub' in this build "
            f"environment (no committed, validated Gemini recording exists -- see "
            f"harness/record_flagship_traces.py), got {source!r}. Refusing to describe a play as "
            "the stub fixture when it is not one -- rerun after checking why a recording seeded."
        )
    run_id = play["trace_ref"].split("/", 1)[1]
    trace = store.read_events(run_id)
    if not trace:
        raise FactsAbort(f"no trace events for {play['trace_ref']} in {data_dir}")

    src = "plays.jsonl (make generate -> harness.seed_plays), read via agents.gate.store.LocalStore"
    return {
        "play_id": play["play_id"],
        "run_id": run_id,
        "source": _val(source, "seeded", src),
        "mechanic": _val(play.get("mechanic"), "seeded", src),
        "mechanic_params": _val(play.get("mechanic_params"), "seeded", src),
        "propose_play_attempts": _val(_propose_play_attempts(trace), "seeded", f"events/{run_id}.jsonl (the flagship play's own recorded trace)"),
    }


# --------------------------------------------------------------------------------------- approve

def _approve_facts(data_dir: Path, as_of: str, play_id: str) -> dict[str, Any]:
    """One real POST /approve through FastAPI's TestClient, against a throwaway visitor sandbox
    (`TAAL_SANDBOX_DIR` pointed at a temp dir that is removed when this function returns, so
    nothing lands in the repo or even survives the run). The base tenant at `data_dir` is only
    ever read by an OverlayStore (agents/gate/store.py); this never writes into it."""
    os.environ["TAAL_DATA_DIR"] = str(data_dir)
    os.environ["TAAL_NOW"] = f"{as_of}T03:30:00Z"
    os.environ.setdefault("TAAL_TENANT_CONFIG", "config/tenant.demo.toml")
    os.environ["TAAL_MODEL_BACKEND"] = "stub"

    with tempfile.TemporaryDirectory(prefix="taal-flagship-facts-sandbox-") as sandbox_dir:
        os.environ["TAAL_SANDBOX_DIR"] = sandbox_dir
        from fastapi.testclient import TestClient

        from services.api.main import app

        client = TestClient(app)
        resp = client.post("/approve", json={"play_id": play_id}, headers={"X-Taal-Visitor": VISITOR_ID})
        if resp.status_code != 200:
            raise FactsAbort(f"POST /approve returned {resp.status_code}: {resp.text[:500]}")
        body = resp.json()

    assignment, forecast = body["assignment"], body["forecast"]
    src = f"POST /approve (FastAPI TestClient, visitor {VISITOR_ID!r}, throwaway TAAL_SANDBOX_DIR)"
    return {
        "visitor": VISITOR_ID,
        "treated_n": _val(assignment["treated_n"], "seeded", src),
        "holdout_n": _val(assignment["holdout_n"], "seeded", src),
        "writeoff_before_inr": _val(forecast["writeoff_before_inr"], "seeded", src),
        "writeoff_after_inr": _val(forecast["writeoff_after_inr"], "seeded", src),
        "forecast_latency_ms": _val(forecast["latency_ms"], "measured, local process, LocalStore + pure-Python forecaster, stub backend -- not the deployed service", src),
    }


# ------------------------------------------------------------------------- deploy.sh + v6 summary

def _configured_replan_deadline_s() -> dict[str, Any]:
    text = DEPLOY_SH.read_text(encoding="utf-8")
    m = re.search(r'gcloud run deploy taal-agents\b.*?--set-env-vars "([^"]*)"', text, re.S)
    if not m:
        raise FactsAbort(f"could not find the 'gcloud run deploy taal-agents ... --set-env-vars' block in {DEPLOY_SH}")
    env_str = m.group(1)
    # taal-agents' --set-env-vars is built up into a shell variable (AGENTS_ENV, so the Vertex
    # Sessions / Firestore cache flags can append to it) rather than written inline; resolve a bare
    # "${VAR}" reference back to that variable's own assignment before looking for the deadline.
    var_ref = re.fullmatch(r"\$\{(\w+)\}", env_str.strip())
    if var_ref:
        var_name = var_ref.group(1)
        vm = re.search(rf'^{re.escape(var_name)}="([^"]*)"', text, re.M)
        if not vm:
            raise FactsAbort(f"--set-env-vars references ${{{var_name}}} but no '{var_name}=\"...\"' assignment was found in {DEPLOY_SH}")
        env_str = vm.group(1)
    m2 = re.search(r"TAAL_PLANNER_DEADLINE_S=([0-9.]+)", env_str)
    if not m2:
        raise FactsAbort(f"TAAL_PLANNER_DEADLINE_S not set in the taal-agents deploy block of {DEPLOY_SH}")
    return _val(float(m2.group(1)), "configured", "infra/deploy.sh (gcloud run deploy taal-agents --set-env-vars, resolved through AGENTS_ENV)")


def _planner_prompt_v6_facts() -> dict[str, Any]:
    if not V6_SUMMARY.exists():
        raise FactsAbort(f"{V6_SUMMARY} does not exist")
    data = json.loads(V6_SUMMARY.read_text(encoding="utf-8"))
    after = data.get("after_prompt_v6") or {}
    model_runs = {gid: r for gid, r in after.items() if r.get("planner_source") == "model"}
    if not model_runs:
        raise FactsAbort(f"no after_prompt_v6 run with planner_source == 'model' in {V6_SUMMARY}")
    elapsed = [r["elapsed_ms"] for r in model_runs.values()]
    rel = str(V6_SUMMARY.relative_to(ROOT))
    label = "measured 2026-09-24, real Vertex"
    return {
        "source_file": rel,
        "model_run_gap_ids": sorted(model_runs),
        "n_model_runs": len(elapsed),
        "min_elapsed_ms": _val(min(elapsed), label, rel),
        "max_elapsed_ms": _val(max(elapsed), label, rel),
    }


# --------------------------------------------------------------------------------------- main

def build_facts(data_dir: Path) -> dict[str, Any]:
    backend = load_models()["backend"]
    if backend != "stub":
        raise FactsAbort(f"TAAL_MODEL_BACKEND resolves to {backend!r}, not 'stub' -- this script describes the seeded scripted-stub fixture and refuses to run under any other backend (see the module docstring).")

    gap = _gap_facts(data_dir)
    play = _flagship_play_facts(data_dir)
    approve = _approve_facts(data_dir, gap["as_of"]["value"], play["play_id"])
    git_commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()

    return {
        "computed_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "git_commit": git_commit,
        "backend": backend,
        "gap_id": GAP_ID,
        "data_dir": str(data_dir),
        "gap": gap,
        "flagship_play": play,
        "approve": approve,
        "configured_replan_deadline_s": _configured_replan_deadline_s(),
        "planner_prompt_v6": _planner_prompt_v6_facts(),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default=os.environ.get("TAAL_DATA_DIR", ".local/data"), help="tenant dir built by `make generate` (default: $TAAL_DATA_DIR or .local/data)")
    ap.add_argument("--out", default=str(DEFAULT_OUT), help=f"output path (default: {DEFAULT_OUT.relative_to(ROOT)})")
    args = ap.parse_args(argv)
    try:
        facts = build_facts(Path(args.data).resolve())
    except FactsAbort as e:
        print(f"flagship_facts: {e}", file=sys.stderr)
        return 1
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(facts, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"flagship_facts: wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
