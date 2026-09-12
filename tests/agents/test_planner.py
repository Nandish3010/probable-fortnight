"""Planner acceptance (harness/checklists/planner_agent.md) in stub mode: schema validity, trajectory,
loop termination, the policy-change beat, and the Cost Governor gate."""
import json
from pathlib import Path

import jsonschema
import pytest

from agents.gate.config import load_tenant
from agents.gate.models import Play
from agents.planner.run import run_planner_async
from agents.planner.tools import REQUIRED_ORDER

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads((ROOT / "docs" / "schemas" / "play.schema.json").read_text())
V2 = (ROOT / "fixtures" / "policy_v2.txt").read_text()


def _run(store, gap_id, **kw):
    import asyncio

    for t in ("gaps", "plays", "products", "nodes", "customers", "affinity", "consent", "segments", "estimator_priors", "play_assignments", "inventory_batches", "inbound", "order_lines", "play_outcomes", "sense_runs", "policy"):
        store._materialise(t)
    if not (store.root / "manifest.json").exists():
        (store.root / "manifest.json").write_bytes((store.base.root / "manifest.json").read_bytes())
    return asyncio.run(run_planner_async(store.root, gap_id, **kw))


def _trajectory(events):
    return [e["function_call"]["name"] for e in events if e.get("function_call")]


def _is_subsequence(needle, hay):
    it = iter(hay)
    return all(any(x == n for x in it) for n in needle)


@pytest.mark.parametrize("gap_id", ["gap_chips_ds07", "gap_tea_ds04", "gap_cola_ds07", "gap_kaju_ds01", "gap_quinoa_out02"])
def test_planted_gap_yields_a_valid_play_within_three_iterations(sandbox, gap_id):
    out = _run(sandbox, gap_id)
    assert out["status"] == "proposed" and out["iterations"] <= 3
    play = out["play"]
    jsonschema.validate(play, SCHEMA, format_checker=jsonschema.FormatChecker())
    Play.model_validate(play)
    assert all(g["passed"] for g in play["guardrails"]) and len(play["guardrails"]) == 8
    assert _is_subsequence(REQUIRED_ORDER, _trajectory(out["events"]))
    assert play["cost"]["pct_of_rupees_at_stake"] <= load_tenant().thresholds["cost_ceiling_pct_of_rupees_at_stake"]


def test_chips_revises_after_margin_floor_failure(sandbox):
    out = _run(sandbox, "gap_chips_ds07")
    texts = [e["text"] for e in out["events"] if e.get("text")]
    assert any(t.startswith("Guardrail failed: margin_floor") for t in texts)
    assert out["iterations"] == 2 and out["play"]["mechanic"] == "bundle"
    assert out["play"]["alternatives"] and out["play"]["alternatives"][0]["mechanic"] == "coupon"


def test_policy_change_changes_the_tea_mechanic(sandbox):
    v1 = _run(sandbox, "gap_tea_ds04")
    v2 = _run(sandbox, "gap_tea_ds04", policy_text=V2, policy_version="v2")
    assert v1["play"]["mechanic"] == "transfer_plus_nudge"
    assert v2["play"]["mechanic"] != v1["play"]["mechanic"]
    assert v2["play"]["policy_version"] == "v2" and v2["play"]["play_id"].endswith("_v2")


def test_cost_governor_skips_small_gaps(sandbox):
    gaps = sandbox.read("gaps")
    small = next(g for g in gaps if g["rupees_at_stake"] < 500)
    out = _run(sandbox, small["gap_id"])
    assert out["status"] == "skipped" and out["play"] is None and out["events"][0]["author"] == "cost_governor"


def test_evalset_batch_schema_validity_and_gate_pass(sandbox):
    """50 largest eligible gaps: >= 95% valid plays after revision, loop <= 3 (checklist rows 1, 2, 5)."""
    gaps = [g for g in sandbox.read("gaps") if g["rupees_at_stake"] >= 500][:50]
    ok = 0
    for g in gaps:
        out = _run(sandbox, g["gap_id"])
        assert out["iterations"] <= 3
        if out["play"]:
            jsonschema.validate(out["play"], SCHEMA, format_checker=jsonschema.FormatChecker())
            ok += 1
    assert ok / len(gaps) >= 0.95, f"{ok}/{len(gaps)}"


def test_evalsets_committed():
    files = list((ROOT / "agents" / "planner" / "evalsets").glob("*.evalset.json"))
    assert len(files) >= 5
    for f in files:
        d = json.loads(f.read_text())
        assert d["eval_cases"][0]["conversation"][0]["intermediate_data"]["tool_uses"][0]["name"] == "get_gap"
