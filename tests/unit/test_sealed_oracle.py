"""The sealed-eval oracle (eval/sealed/oracle.py): model-free, legal by construction, deterministic."""
import json
import os
from pathlib import Path

import pytest

from agents.gate.store import LocalStore
from eval.sealed import oracle

ROOT = Path(__file__).resolve().parents[2]
DATA = Path(os.environ.get("TAAL_DATA_DIR", ROOT / ".local" / "data"))
pytestmark = pytest.mark.skipif(not (DATA / "manifest.json").exists(), reason="needs `make generate`")

TEA = "gap_tea_ds04"


def _clearing_gaps(n: int) -> list[str]:
    rows = [g for g in LocalStore(DATA).read("gaps") if g["type"] in ("online_sellby_breach", "expiry_writeoff") and g["rupees_at_stake"] >= 500]
    return [TEA] + [g["gap_id"] for g in rows if g["gap_id"] != TEA][:: max(1, len(rows) // n)][:n]


@pytest.fixture(scope="module")
def solved() -> dict:
    return oracle.solve_gaps(DATA, _clearing_gaps(5))


def test_oracle_never_returns_a_guardrail_failing_play(solved):
    ctx = oracle.cached_context(DATA, "test")
    for gid, res in solved.items():
        assert res["top3"] and res["best"] in res["per_class_best"].values()
        for entry in res["per_class_best"].values():
            if entry["class"] in ("do_nothing", "blanket_markdown"):
                continue
            assert entry["legal"] is True
            assert len(entry["guardrails"]) == 8 and all(g["passed"] for g in entry["guardrails"]), (gid, entry["guardrails"])
            assert entry["recovery_inr_play"] == entry["recovery_inr"]  # propose_play's own re-derivation agrees with the score
        # a fresh, independent pass of the product's gate over the best play's params
        best = res["best"]
        if best["class"] not in ("do_nothing", "blanket_markdown"):
            cand = {"class": best["class"], "mechanic": best["mechanic"], "mechanic_params": best["mechanic_params"], "segments": best["segments"], "holdout": best["holdout_fraction"]}
            from dataclasses import replace

            from agents.planner.context import reset_context, set_context
            sb = oracle._Sandbox(ctx.store)
            token = set_context(ctx)
            try:
                enum = oracle.enumerate_candidates(ctx, gid)
                v = oracle.legal_play(ctx, replace(ctx, store=sb.store), enum, cand)
            finally:
                reset_context(token)
                sb.close()
            assert v["legal"], v["errors"]


def test_demo_tea_gap_oracle_at_least_the_recorded_play(solved):
    recorded = next(json.loads(r["play_json"]) for r in LocalStore(DATA).read("plays") if r["play_id"] == "play_tea_ds04_v1")
    cf = recorded["counterfactuals"]
    hero = round(cf["do_nothing_inr"] + cf["play_net_inr"], 2)
    assert hero == pytest.approx(9191.29, abs=0.01)
    assert solved[TEA]["best"]["recovery_inr"] >= hero
    assert solved[TEA]["blanket20_recovery_inr"] == pytest.approx(cf["do_nothing_inr"] - cf["blanket_markdown_inr"], abs=0.01)


def test_baselines_and_ordering(solved):
    for res in solved.values():
        assert res["do_nothing_recovery_inr"] == 0.0
        rec = [p["recovery_inr"] for p in res["top3"]]
        assert rec == sorted(rec, reverse=True)
        assert len({p["class"] for p in res["top3"]}) == len(res["top3"])


def test_determinism():
    a = oracle.solve_gap(DATA, TEA)
    b = oracle.solve_gap(DATA, TEA)
    assert json.dumps(a, sort_keys=True, default=str) == json.dumps(b, sort_keys=True, default=str)


def test_estimator_ignores_transfer_node_and_holdout():
    """The oracle's score cache and tie-break rely on this: the estimator reads neither."""
    ctx = oracle.cached_context(DATA, "test")
    from agents.gate.estimator import estimate
    from agents.planner import tools as pt
    from agents.planner.context import reset_context, set_context

    token = set_context(ctx)
    try:
        enum = oracle.enumerate_candidates(ctx, TEA)
        tr = [c for c in enum["candidates"] if c["class"] == "transfer_plus_nudge"]
        by_key: dict = {}
        for c in tr:
            k = (c["mechanic_params"]["transfer_units"], tuple(c["segments"]))
            by_key.setdefault(k, set()).add(c["recovery"])
        assert all(len(v) == 1 for v in by_key.values())
        c = tr[0]
        d = oracle._build_draft(ctx, enum["gap"], enum["audiences"], {"mechanic": c["mechanic"], "mechanic_params": c["mechanic_params"]}, tuple(c["segments"]), 0.05)
        d2 = oracle._build_draft(ctx, enum["gap"], enum["audiences"], {"mechanic": c["mechanic"], "mechanic_params": {**c["mechanic_params"], "transfer_to_node": "OUT-02"}}, tuple(c["segments"]), 0.9)
        e1 = estimate(d, pt._estimator_context(ctx, {**d, "audience": {**d["audience"], "size_after_consent": c["audience_after_consent"]}}))
        e2 = estimate(d2, pt._estimator_context(ctx, {**d2, "audience": {**d2["audience"], "size_after_consent": c["audience_after_consent"]}}))
        assert e1 == e2
    finally:
        reset_context(token)
