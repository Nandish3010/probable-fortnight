"""The holdout seed is code: propose_play sets it to seed-<final play id>, whatever the model wrote
and whichever path produced the play (model, rules fallback, a pinned live id)."""
import json
from pathlib import Path
from types import SimpleNamespace

from agents.planner import tools as pt
from agents.planner.context import PlannerContext, reset_context, set_context
from agents.planner.deterministic import deterministic_plan
from tests.agents.test_planner_source import _run

ROOT = Path(__file__).resolve().parents[2]
GAP = "gap_tea_ds04"


def _context(sandbox, **kw):
    for t in ("gaps", "plays", "products", "nodes", "customers", "affinity", "consent", "segments", "estimator_priors", "play_assignments", "inventory_batches", "inbound", "order_lines", "play_outcomes", "sense_runs", "policy"):
        sandbox._materialise(t)
    if not (sandbox.root / "manifest.json").exists():
        (sandbox.root / "manifest.json").write_bytes((sandbox.base.root / "manifest.json").read_bytes())
    return PlannerContext.build(sandbox.root, run_id="seed-test", **kw)


def test_a_model_written_seed_is_replaced_by_one_derived_from_the_play_id(sandbox):
    play = json.loads((ROOT / "fixtures" / "plays" / "valid" / "play_tea_ds04_v2.json").read_text(encoding="utf-8"))
    play["holdout"]["seed"] = "seed-whatever-the-model-wrote"
    tok = set_context(_context(sandbox))
    try:
        pt.propose_play(play, SimpleNamespace(state={}, actions=SimpleNamespace(escalate=False)))
    finally:
        reset_context(tok)
    assert play["holdout"]["seed"] == f"seed-{play['play_id']}"


def test_a_pinned_live_id_and_its_seed_follow_each_other_on_the_rules_fallback_path(sandbox):
    ctx = _context(sandbox, play_id="play_tea_ds04_v1_live")
    tok = set_context(ctx)
    try:
        play = deterministic_plan(ctx, GAP)
    finally:
        reset_context(tok)
    assert play["play_id"] == "play_tea_ds04_v1_live" and play["holdout"]["seed"] == "seed-play_tea_ds04_v1_live"


def test_a_pinned_run_stores_the_play_under_the_pinned_id_with_its_own_seed(sandbox):
    out = _run(sandbox, GAP, play_id="play_tea_ds04_v1_live")
    assert out["play"]["play_id"] == "play_tea_ds04_v1_live"
    stored = json.loads(sandbox.find("plays", play_id="play_tea_ds04_v1_live")[-1]["play_json"])
    assert stored["holdout"]["seed"] == "seed-play_tea_ds04_v1_live"
    original = json.loads(sandbox.find("plays", play_id="play_tea_ds04_v1")[-1]["play_json"])
    assert original["holdout"]["seed"] != stored["holdout"]["seed"]
