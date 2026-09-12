"""Measure at the table level after an approve + a real order through the customer agent."""
import asyncio
from datetime import UTC, datetime

from agents.customer.chat import reset_sessions, run_chat_async
from agents.gate.config import load_tenant
from data.bigquery.local import ASSERTIONS_DIR, build, run_assertion
from jobs.measure.run import run_measure
from services.api.approve import approve


def test_measure_counts_a_treated_responder_and_updates_priors(sandbox):
    approve(sandbox, load_tenant(), "play_chips_ds07_v1", datetime(2026, 9, 12, 9, 0, tzinfo=UTC))
    reset_sessions()
    asyncio.run(run_chat_async(sandbox, "CUST-MEENA:web", "Any offers?", now_iso="2026-09-12T09:05:00Z"))
    env = asyncio.run(run_chat_async(sandbox, "CUST-MEENA:web", "add:SKU-MASALA-CHIPS-200G", now_iso="2026-09-12T09:06:00Z"))[0]
    assert "ORD-" in env["text"]
    for t in ("plays", "play_assignments", "order_lines", "play_outcomes", "estimator_priors", "products"):
        sandbox._materialise(t)
    before = {(r["mechanic"], r["category"]): (r["alpha"], r["beta"]) for r in sandbox.read("estimator_priors")}
    out = run_measure(sandbox.root, computed_at="2026-09-19T00:00:00Z")
    assert out["measured"] == 1
    treated = next(r for r in sandbox.read("play_outcomes") if r["arm"] == "treated")
    assert treated["responders"] == 1 and treated["units_target_lot"] >= 1 and treated["status"] == "measured"
    assert treated["waste_kg_est"] > 0 and treated["emissions_factor_kgco2e_per_kg"] == 2.5
    after = {(r["mechanic"], r["category"]): (r["alpha"], r["beta"]) for r in sandbox.read("estimator_priors")}
    a0, b0 = before[("bundle", "snacks")]
    a1, b1 = after[("bundle", "snacks")]
    assert a1 == a0 + 1 and b1 == b0 + treated["customers"] - 1
    assert next(r for r in sandbox.read("plays") if r["play_id"] == "play_chips_ds07_v1")["status"] == "measured"
    con = build(sandbox)
    assert run_assertion(con, ASSERTIONS_DIR / "no_lift_without_holdout.sql") == []
