"""Tool contracts under docs/schemas/tools validate the live tool outputs in stub mode."""
import json
from pathlib import Path

import jsonschema
import pytest

from agents.planner import tools as pt
from agents.planner.context import PlannerContext, reset_context, set_context

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
    for t in ("get_customer_context", "get_stock", "find_substitutes", "apply_offer", "place_order", "record_stop"):
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
