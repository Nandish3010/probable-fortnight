import math

from hypothesis import given, settings
from hypothesis import strategies as st

from agents.gate.estimator import (
    EstimatorContext,
    GapFacts,
    Product,
    beta_cdf,
    beta_quantile,
    counterfactuals,
    estimate,
    unit_economics,
    update_prior,
)

CHIPS = Product("SKU-MASALA-CHIPS-200G", "snacks", unit_cost=25.0, list_price=30.0, margin_floor_pct=8.0)


def ctx(audience=315, units_at_risk=368, **kw) -> EstimatorContext:
    return EstimatorContext(product=CHIPS, gap=GapFacts(units_at_risk=units_at_risk, rupees_at_stake=units_at_risk * 25.0, evidence={"projected_sellthrough": 72.23}), audience_size_after_consent=audience, **kw)


def test_beta_cdf_matches_known_values():
    assert abs(beta_cdf(0.5, 1, 1) - 0.5) < 1e-9
    assert abs(beta_cdf(0.05, 1, 19) - (1 - 0.95**19)) < 1e-9
    q = beta_quantile(0.5, 2, 2)
    assert abs(q - 0.5) < 1e-8


def test_coupon_arithmetic_matches_spreadsheet():
    c = ctx()
    out = estimate({"mechanic": "coupon", "mechanic_params": {"discount_pct": 15}, "audience": {"segment_ids": ["seg_1"]}}, c)
    eo = out["expected_outcome"]
    rate = 1 / 20
    units = 315 * rate * 1.0
    assert eo["units"] == round(units, 2)
    assert eo["discount_cost_inr"] == round(units * 30 * 0.15, 2)
    assert eo["margin_inr"] == round(units * (30 - 4.5 - 25), 2)
    assert eo["waste_avoided_inr"] == round(min(units, 368) * 25, 2)
    assert eo["ci_low"] <= eo["units"] <= eo["ci_high"]
    cf = out["counterfactuals"]
    assert cf["do_nothing_inr"] == 368 * 25.0
    assert cf["blanket_markdown_pct"] == 20.0


def test_counterfactual_blanket_markdown_formula():
    c = ctx(markdown_elasticity=4.0)
    cf = counterfactuals({"mechanic": "coupon", "mechanic_params": {}}, c)
    baseline = 72.23
    given_away = baseline * 0.2 * 30
    remaining = max(0.0, 368 - baseline * 0.2 * 4.0) * 25
    assert cf["blanket_markdown_inr"] == round(given_away + remaining, 2)


def test_bundle_and_transfer_economics():
    c = ctx(bundle_partner_unit_cost=30.0, bundle_partner_list_price=40.0)
    econ = unit_economics("bundle", {"bundle_price": 66}, c)
    assert econ["margin"] == 66 - 55
    out = estimate({"mechanic": "transfer_plus_nudge", "mechanic_params": {"transfer_units": 100}, "audience": {"segment_ids": ["seg_1"]}}, ctx(transfer_cost_per_unit=2.0))
    eo = out["expected_outcome"]
    assert eo["units"] <= 100
    assert eo["margin_inr"] == round(eo["waste_avoided_inr"] - 2.0 * 100, 2)
    assert eo["discount_cost_inr"] == 0.0


def test_prior_update_is_exact_counts():
    assert update_prior(1.0, 19.0, 7, 93) == (8.0, 112.0)


def test_priors_lookup_falls_back_to_weak_default():
    c = ctx(priors={("coupon", "snacks", "seg_9"): (10.0, 90.0, 100)})
    out = estimate({"mechanic": "coupon", "mechanic_params": {"discount_pct": 10}, "audience": {"segment_ids": ["seg_1"]}}, c)
    assert out["expected_outcome"]["prior_n"] == 20.0
    out2 = estimate({"mechanic": "coupon", "mechanic_params": {"discount_pct": 10}, "audience": {"segment_ids": ["seg_9"]}}, c)
    assert out2["expected_outcome"]["measured_n"] == 100


@settings(max_examples=200, deadline=None)
@given(price=st.floats(10, 1000), cost_frac=st.floats(0.3, 0.99), pct=st.floats(0, 60))
def test_margin_after_discount_never_below_floor_when_gate_passes(price, cost_frac, pct):
    from agents.gate.guardrails import GuardrailContext, rule_margin_floor

    p = Product("X", "snacks", unit_cost=price * cost_frac, list_price=price, margin_floor_pct=8.0)
    res = rule_margin_floor({"mechanic": "coupon", "mechanic_params": {"discount_pct": pct}}, GuardrailContext(product=p))
    net = price * (1 - pct / 100)
    margin_pct = (net - p.unit_cost) / net * 100 if net > 0 else -100
    if res["passed"]:
        assert margin_pct >= 8.0 - 1e-9
    else:
        assert margin_pct < 8.0


def test_ci_bounds_monotone_in_audience():
    a = estimate({"mechanic": "coupon", "mechanic_params": {"discount_pct": 10}, "audience": {"segment_ids": ["s"]}}, ctx(audience=100))["expected_outcome"]
    b = estimate({"mechanic": "coupon", "mechanic_params": {"discount_pct": 10}, "audience": {"segment_ids": ["s"]}}, ctx(audience=1000))["expected_outcome"]
    assert b["units"] > a["units"] and b["ci_high"] > a["ci_high"]
    assert not math.isnan(b["ci_low"])
