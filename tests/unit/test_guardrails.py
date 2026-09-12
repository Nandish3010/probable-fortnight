import copy

from agents.gate import guardrails as gr
from agents.gate.estimator import Product
from agents.gate.models import GUARDRAIL_RULES

CHIPS = Product("SKU-MASALA-CHIPS-200G", "snacks", 25.0, 30.0, 8.0)


def draft(**over):
    d = {
        "objective": "clear_online_sellby", "mechanic": "coupon", "mechanic_params": {"discount_pct": 5},
        "target": {"sku": "SKU-MASALA-CHIPS-200G", "node_ids": ["DS-07"], "deadline_type": "online_sellby"},
        "audience": {"segment_ids": ["seg_1"], "purpose": "marketing", "size_before_consent": 100, "size_after_consent": 80},
        "channel": "web_chat", "copy": {"copy_status": "pending", "variants": []},
        "holdout": {"fraction": 0.1, "seed": "seed-x", "min_treated_n": 20},
        "rationale": "80 consented customers, expected 4 units, margin ₹20.", "citations": [{"type": "gap", "ref": "gap_x"}],
        "expected_outcome": {"units": 4.0, "margin_inr": 20.0},
    }
    d.update(over)
    return d


def ctx(**kw) -> gr.GuardrailContext:
    return gr.GuardrailContext(product=CHIPS, **kw)


def test_all_eight_rules_run_and_report():
    out = gr.check(draft(), ctx())
    assert [r["rule"] for r in out["results"]] == list(GUARDRAIL_RULES)
    assert out["all_passed"]


def test_margin_floor_pass_and_fail():
    assert gr.rule_margin_floor(draft(mechanic_params={"discount_pct": 5}), ctx())["passed"]
    assert not gr.rule_margin_floor(draft(mechanic_params={"discount_pct": 15}), ctx())["passed"]
    assert gr.rule_margin_floor(draft(mechanic="bundle", mechanic_params={"bundle_price": 66}), ctx(bundle_partner_unit_cost=30, bundle_partner_list_price=40))["passed"]
    assert not gr.rule_margin_floor(draft(mechanic="bundle", mechanic_params={"bundle_price": 58}), ctx(bundle_partner_unit_cost=30, bundle_partner_list_price=40))["passed"]


def test_frequency_cap_pass_and_fail():
    c = ctx(audience_customer_ids=["a", "b"], recent_plays_count={"a": 2})
    assert not gr.rule_frequency_cap(draft(), c)["passed"]
    assert gr.rule_frequency_cap(draft(), ctx(audience_customer_ids=["a"], recent_plays_count={"a": 1}))["passed"]
    assert gr.rule_frequency_cap(draft(), ctx())["passed"]


def test_consent_required_variants():
    assert not gr.rule_consent_required(draft(audience={"segment_ids": ["s"], "purpose": "analytics", "size_before_consent": 1, "size_after_consent": 1}), ctx())["passed"]
    assert not gr.rule_consent_required(draft(audience={"segment_ids": ["s"], "purpose": "marketing", "size_before_consent": 10, "size_after_consent": 11}), ctx())["passed"]
    assert not gr.rule_consent_required(draft(), ctx(audience_customer_ids=["a", "b"], consented_customer_ids=frozenset({"a"})))["passed"]
    assert gr.rule_consent_required(draft(), ctx(audience_customer_ids=["a"], consented_customer_ids=frozenset({"a"})))["passed"]
    assert gr.rule_consent_required(draft(channel="outlet"), ctx())["passed"]


def test_sellby_disclosure_variants():
    assert gr.rule_sellby_disclosure(draft(objective="prevent_stockout", target={"sku": "x", "node_ids": ["n"], "deadline_type": "lead_time"}), ctx())["passed"]
    assert gr.rule_sellby_disclosure(draft(), ctx())["passed"]  # pending copy
    v = draft(copy={"copy_status": "generated", "variants": [{"segment_id": "s", "language": "en", "text": "x", "disclosure_included": False}]})
    assert not gr.rule_sellby_disclosure(v, ctx())["passed"]
    v2 = draft(copy={"copy_status": "generated", "variants": [{"segment_id": "s", "language": "en", "text": "x", "disclosure_included": True}]})
    assert gr.rule_sellby_disclosure(v2, ctx())["passed"]
    assert not gr.rule_sellby_disclosure(draft(copy={"copy_status": "generated", "variants": []}), ctx())["passed"]


def test_subscription_protect_variants():
    assert gr.rule_subscription_protect(draft(mechanic="preorder"), ctx(audience_customer_ids=["a"], subscribers_for_sku=frozenset({"a"})))["passed"]
    assert not gr.rule_subscription_protect(draft(), ctx(audience_customer_ids=["a"], subscribers_for_sku=frozenset({"a"})))["passed"]
    assert gr.rule_subscription_protect(draft(), ctx(audience_customer_ids=["b"], subscribers_for_sku=frozenset({"a"})))["passed"]
    assert gr.rule_subscription_protect(draft(), ctx())["passed"]


def test_no_cannibalise_stockout_variants():
    assert not gr.rule_no_cannibalise_stockout(draft(), ctx(stockout_gap_skus_at_node=frozenset({"SKU-MASALA-CHIPS-200G"})))["passed"]
    assert gr.rule_no_cannibalise_stockout(draft(objective="prevent_stockout"), ctx(stockout_gap_skus_at_node=frozenset({"SKU-MASALA-CHIPS-200G"})))["passed"]
    assert gr.rule_no_cannibalise_stockout(draft(), ctx())["passed"]


def test_holdout_required_variants():
    assert gr.rule_holdout_required(draft(), ctx())["passed"]
    assert not gr.rule_holdout_required(draft(holdout={"fraction": 0.01, "seed": "s", "min_treated_n": 20}), ctx())["passed"]
    assert not gr.rule_holdout_required(draft(holdout={"fraction": 0.1, "seed": "", "min_treated_n": 20}), ctx())["passed"]
    assert not gr.rule_holdout_required(draft(holdout={"fraction": 0.1, "seed": "s", "min_treated_n": 0}), ctx())["passed"]
    assert not gr.rule_holdout_required(draft(holdout={}), ctx())["passed"]


def test_cite_or_drop_rejects_an_uncited_number():
    d = draft(rationale="We expect 4 units and 999 rupees of margin.")
    res = gr.rule_cite_or_drop(d, ctx())
    assert not res["passed"] and "999" in res["detail"]
    assert gr.rule_cite_or_drop(draft(), ctx())["passed"]


def test_cite_or_drop_unresolved_citation():
    res = gr.rule_cite_or_drop(draft(), ctx(resolve_citation=lambda t, r: False))
    assert not res["passed"] and "do not resolve" in res["detail"]


def test_numbers_in_text_ignores_ids_and_dates():
    assert gr.numbers_in_text("Lot B-CHIPS-DS07-01 at DS-07 on 2026-09-18, 368 units, 9200 rupees, policy v1") == [368.0, 9200.0]


def test_check_is_pure():
    d = draft()
    before = copy.deepcopy(d)
    gr.check(d, ctx())
    assert d == before
