"""Tool contracts under docs/schemas/tools validate the live tool outputs in stub mode."""
import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

import jsonschema
import pytest

from agents.customer import tools as ct
from agents.customer.context import CustomerContext
from agents.customer.context import reset_context as reset_customer_context
from agents.customer.context import set_context as set_customer_context
from agents.gate.config import load_tenant
from agents.planner import tools as pt
from agents.planner.context import PlannerContext, reset_context, set_context
from services.api.approve import approve

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "docs" / "schemas" / "tools"


def _schema(name: str, part: str) -> dict:
    d = json.loads((TOOLS / f"{name}.schema.json").read_text())
    body = d["properties"][part] if "properties" in d and part in d["properties"] else d[part]
    return {**body, "$defs": d.get("$defs", {})}


def test_every_tool_has_a_contract():
    names = {p.name for p in TOOLS.glob("*.schema.json")}
    for t in ("get_gap", "get_candidate_audiences", "estimate_outcome", "check_guardrails", "get_past_plays", "propose_play"):
        assert f"planner.{t}.schema.json" in names
    for t in ("get_customer_context", "get_stock", "find_substitutes", "apply_offer", "place_order", "record_stop", "list_products"):
        assert f"customer.{t}.schema.json" in names


@pytest.fixture
def planner_ctx(base_store):
    ctx = PlannerContext.build(base_store.root, run_id="contract-test")
    tok = set_context(ctx)
    yield ctx
    reset_context(tok)


def test_planner_tool_outputs_validate(planner_ctx):
    gap = pt.get_gap("gap_chips_ds07")
    jsonschema.validate(gap, {**_schema("planner.get_gap", "output")}, format_checker=jsonschema.FormatChecker())
    auds = pt.get_candidate_audiences(gap["sku"], [gap["node_id"]], "clear_online_sellby")
    jsonschema.validate(auds, _schema("planner.get_candidate_audiences", "output"))
    past = pt.get_past_plays(gap["sku"], "snacks", "coupon")
    jsonschema.validate(past, _schema("planner.get_past_plays", "output"))
    from agents.planner import drafting

    draft = drafting.build_draft(gap, auds, {"mechanic": "coupon", "mechanic_params": {"discount_pct": 5}}, "v1", "contract-test", 0.1, 20, ["en", "kn"], "2026-09-12")
    est = pt.estimate_outcome(draft)
    jsonschema.validate(est, _schema("planner.estimate_outcome", "output"))
    full = drafting.finish_draft(draft, gap, est, auds, [], planner_ctx.policy_text)
    chk = pt.check_guardrails(full)
    jsonschema.validate(chk, _schema("planner.check_guardrails", "output"))
    assert len(chk["results"]) == 8


def test_customer_tool_outputs_validate(sandbox):
    """Every customer tool's return value validates against its schema, in the shapes an actual
    conversation exercises (a real stock hit, a real out-of-stock substitution, a real bundle
    redemption). This is what would have caught the `place_order` `lines` field being silently
    dropped by a stray `return` statement: the schema said it existed, nothing checked that it did."""
    tenant = load_tenant()
    play_id = "play_chips_ds07_v1"
    approve(sandbox, tenant, play_id, datetime(2026, 9, 12, 9, 0, tzinfo=UTC))
    ctx = CustomerContext.build(sandbox, "CUST-MEENA", "2026-09-12T09:05:00Z", tenant)
    tok = set_customer_context(ctx)
    try:
        cc = ct.get_customer_context("CUST-MEENA")
        jsonschema.validate(cc, _schema("customer.get_customer_context", "output"), format_checker=jsonschema.FormatChecker())
        assert cc["pending_offers"], "fixture drifted: expected a pending offer on the approved chips play"

        st_hit = ct.get_stock("SKU-MASALA-CHIPS-200G", "DS-07")
        jsonschema.validate(st_hit, _schema("customer.get_stock", "output"), format_checker=jsonschema.FormatChecker())
        assert st_hit["qty"] > 0

        st_miss = ct.get_stock("SKU-COLA-ZERO-500ML", "DS-07")
        jsonschema.validate(st_miss, _schema("customer.get_stock", "output"), format_checker=jsonschema.FormatChecker())
        assert st_miss["qty"] == 0

        subs = ct.find_substitutes("SKU-COLA-ZERO-500ML", "DS-07")
        jsonschema.validate(subs, _schema("customer.find_substitutes", "output"), format_checker=jsonschema.FormatChecker())
        assert subs

        browse = ct.list_products("chips", "DS-07")
        jsonschema.validate(browse, _schema("customer.list_products", "output"), format_checker=jsonschema.FormatChecker())
        assert browse["products"]

        offer = ct.apply_offer(play_id, "CUST-MEENA")
        jsonschema.validate(offer, _schema("customer.apply_offer", "output"), format_checker=jsonschema.FormatChecker())
        assert offer["ok"]

        order = asyncio.run(ct.place_order("CUST-MEENA", "DS-07", [{"sku": "SKU-MASALA-CHIPS-200G", "qty": 1}, {"sku": offer["bundle_sku"], "qty": 1}], play_id))
        jsonschema.validate(order, _schema("customer.place_order", "output"), format_checker=jsonschema.FormatChecker())
        assert {ln["sku"] for ln in order["lines"]} == {"SKU-MASALA-CHIPS-200G", offer["bundle_sku"]}, "bundle partner must be named, not just totalled"

        stop = ct.record_stop("CUST-MEENA", "web_chat")
        jsonschema.validate(stop, _schema("customer.record_stop", "output"), format_checker=jsonschema.FormatChecker())
    finally:
        reset_customer_context(tok)


def test_customer_tool_output_schemas_are_not_vacuous():
    """Every customer.*.schema.json output actually names its fields (guards against a schema file
    that validates anything because someone forgot to list `required`/`properties`)."""
    names = ("get_customer_context", "get_stock", "find_substitutes", "apply_offer", "place_order", "record_stop", "list_products")
    for name in names:
        schema = _schema(f"customer.{name}", "output")
        assert schema.get("properties") or schema.get("items"), f"customer.{name} output schema has no properties/items"
