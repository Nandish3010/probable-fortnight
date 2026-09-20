"""Measure at the table level after an approve + a real order through the customer agent."""
import asyncio
from datetime import UTC, datetime

from agents.customer.chat import reset_sessions, run_chat_async
from agents.gate.config import load_tenant
from agents.stylist.context import StylistContext
from agents.stylist.context import reset_context as reset_stylist_context
from agents.stylist.context import set_context as set_stylist_context
from agents.stylist.tools import place_order as stylist_place_order
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


def test_measure_places_an_apparel_order_without_crashing_on_a_grocery_only_lookup(sandbox):
    """The apparel analogue of the test above, sized to prove two things: (1) the unified
    catalogue (agents/gate/store.py::load_catalogue) resolves an apparel sku in the same
    run_measure call that resolves grocery skus, and (2) a play whose small, real-asker audience
    happens to hash zero customers into the holdout arm is skipped, not a crash that would take
    down measurement for every other play in the tenant (jobs/measure/run.py's MeasureError
    catch)."""
    tenant = load_tenant()
    approve(sandbox, tenant, "play_blazer_ds07_v1", datetime(2026, 9, 12, 9, 0, tzinfo=UTC))
    treated = [a["customer_id"] for a in sandbox.read("play_assignments") if a["play_id"] == "play_blazer_ds07_v1" and a["arm"] == "treated"]
    holdout = [a["customer_id"] for a in sandbox.read("play_assignments") if a["play_id"] == "play_blazer_ds07_v1" and a["arm"] == "holdout"]
    assert treated, "fixture drifted: expected at least one real, consented, treated asker"
    ctx = StylistContext.build(sandbox, treated[0], "2026-09-12T09:05:00Z", tenant)
    tok = set_stylist_context(ctx)
    try:
        order = asyncio.run(stylist_place_order(treated[0], "DS-07", [{"sku": "APP-BLAZER-BLACK-U", "qty": 1}], "play_blazer_ds07_v1"))
    finally:
        reset_stylist_context(tok)
    assert order["order_id"]
    for t in ("plays", "play_assignments", "order_lines", "play_outcomes", "estimator_priors", "products", "apparel_products"):
        sandbox._materialise(t)
    out = run_measure(sandbox.root, computed_at="2026-09-19T00:00:00Z")
    apparel_rows = [r for r in sandbox.read("order_lines") if r["sku"] == "APP-BLAZER-BLACK-U"]
    assert apparel_rows, "the order must have actually landed in order_lines"
    if holdout:
        # this seeded scenario's real hash happened to land at least one holdout customer: the
        # play measures like any other, just with a smaller audience than a forecast-driven one.
        assert "play_blazer_ds07_v1" not in out["skipped"]
    else:
        # zero holdout by chance on a 6-8 person audience is plausible, not a bug -- the guardrail
        # in measure_play correctly refuses to fabricate a lift, and run_measure does not let that
        # refusal crash measurement for grocery plays measured in the same call.
        assert "play_blazer_ds07_v1" in out["skipped"]
    assert out["plays"] >= 1
