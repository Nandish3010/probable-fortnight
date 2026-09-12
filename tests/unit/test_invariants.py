"""Runtime invariant (DECISIONS §17.5): an independent recomputation of a play's money numbers
must agree with what the estimator itself produced, for every mechanic, and must reject a play
whose reported numbers have drifted from what its own units and mechanic params imply."""
from agents.gate.estimator import EstimatorContext, GapFacts, Product, estimate
from agents.gate.invariants import check_play_money, recompute_play_money

CHIPS = Product("SKU-MASALA-CHIPS-200G", "snacks", unit_cost=25.0, list_price=30.0, margin_floor_pct=8.0)


def ctx(**kw) -> EstimatorContext:
    return EstimatorContext(product=CHIPS, gap=GapFacts(units_at_risk=368, rupees_at_stake=368 * 25.0), audience_size_after_consent=315, **kw)


def _play(mechanic: str, params: dict, expected_outcome: dict) -> dict:
    return {"mechanic": mechanic, "mechanic_params": params, "expected_outcome": expected_outcome}


def test_agrees_with_the_real_estimator_for_every_discount_mechanic():
    for mechanic, params in [("coupon", {"discount_pct": 15}), ("outlet_markdown", {"markdown_pct": 20})]:
        out = estimate({"mechanic": mechanic, "mechanic_params": params, "audience": {"segment_ids": ["seg_1"]}}, ctx())
        play = _play(mechanic, params, out["expected_outcome"])
        assert check_play_money(play, CHIPS.unit_cost, CHIPS.list_price, 368) == []


def test_agrees_with_the_real_estimator_for_bundle():
    c = ctx(bundle_partner_unit_cost=30.0, bundle_partner_list_price=40.0)
    params = {"bundle_price": 61}
    out = estimate({"mechanic": "bundle", "mechanic_params": params, "audience": {"segment_ids": ["seg_1"]}}, c)
    play = _play("bundle", params, out["expected_outcome"])
    assert check_play_money(play, CHIPS.unit_cost, CHIPS.list_price, 368, bundle_partner_unit_cost=30.0, bundle_partner_list_price=40.0) == []


def test_agrees_with_the_real_estimator_for_transfer_plus_nudge():
    out = estimate({"mechanic": "transfer_plus_nudge", "mechanic_params": {}, "audience": {"segment_ids": ["seg_1"]}}, ctx(transfer_cost_per_unit=3.0))
    play = _play("transfer_plus_nudge", {}, out["expected_outcome"])
    assert check_play_money(play, CHIPS.unit_cost, CHIPS.list_price, 368, transfer_cost_per_unit=3.0) == []


def test_agrees_with_the_real_estimator_for_a_plain_mechanic():
    out = estimate({"mechanic": "usual_order_addon", "mechanic_params": {}, "audience": {"segment_ids": ["seg_1"]}}, ctx())
    play = _play("usual_order_addon", {}, out["expected_outcome"])
    assert check_play_money(play, CHIPS.unit_cost, CHIPS.list_price, 368) == []


def test_rejects_a_play_whose_reported_margin_has_drifted():
    out = estimate({"mechanic": "coupon", "mechanic_params": {"discount_pct": 15}, "audience": {"segment_ids": ["seg_1"]}}, ctx())
    eo = dict(out["expected_outcome"])
    eo["margin_inr"] = eo["margin_inr"] + 50.0  # a bug (or a tampered draft) inflating the margin
    play = _play("coupon", {"discount_pct": 15}, eo)
    problems = check_play_money(play, CHIPS.unit_cost, CHIPS.list_price, 368)
    assert problems and any("margin_inr" in p for p in problems)


def test_rejects_a_play_with_a_missing_or_non_numeric_expected_outcome_field():
    play = _play("coupon", {"discount_pct": 15}, {"units": 15.75, "discount_cost_inr": 70.88})  # margin_inr missing
    problems = check_play_money(play, CHIPS.unit_cost, CHIPS.list_price, 368)
    assert any("margin_inr" in p for p in problems)


def test_recompute_is_pure_and_deterministic():
    play = _play("coupon", {"discount_pct": 15}, {"units": 15.75})
    a = recompute_play_money(play, CHIPS.unit_cost, CHIPS.list_price, 368)
    b = recompute_play_money(play, CHIPS.unit_cost, CHIPS.list_price, 368)
    assert a == b
