"""The `markdown` mechanic, the one demand model (est-v2) and the beats_markdown gate check."""
import dataclasses
import json

import pytest

from agents.gate import guardrails as gr
from agents.gate.assignment import assign
from agents.gate.config import TenantConfig, load_tenant
from agents.gate.estimator import (
    EstimatorContext,
    GapFacts,
    Product,
    best_markdown,
    counterfactuals,
    estimate,
    recovery_of,
    units_sold_at_discount,
)

CHIPS = Product("SKU-MASALA-CHIPS-200G", "snacks", unit_cost=25.0, list_price=30.0, margin_floor_pct=8.0)
WIDGET = Product("SKU-WIDGET", "snacks", unit_cost=25.0, list_price=50.0, margin_floor_pct=8.0)  # roomy margin: every depth clears the floor
TEA = Product("SKU-TEA", "premium_tea", unit_cost=340.0, list_price=450.0, margin_floor_pct=12.0)


def ctx(product=CHIPS, audience=315, units_at_risk=368, baseline=72.23, **kw) -> EstimatorContext:
    kw.setdefault("markdown_elasticity", 4.0)
    return EstimatorContext(product=product, gap=GapFacts(units_at_risk=units_at_risk, rupees_at_stake=units_at_risk * product.unit_cost, evidence={"projected_sellthrough": baseline}), audience_size_after_consent=audience, baseline_forecast_units=baseline, **kw)


def draw(mechanic, **params):
    return {"mechanic": mechanic, "mechanic_params": params, "audience": {"segment_ids": ["seg_1"]}}


# ------------------------------------------------------------------ one demand model

def test_units_sold_at_discount_formula_and_caps():
    c = ctx()
    assert units_sold_at_discount(72.23, 0.2, c) == pytest.approx(72.23 * 0.2 * 4.0)
    assert units_sold_at_discount(72.23, 0.0, c) == 0.0
    assert units_sold_at_discount(1000.0, 0.5, c) == 368  # capped by units at risk
    ramp = ctx(markdown_ramp_days=10.0, days_left=5.0)
    assert units_sold_at_discount(72.23, 0.2, ramp) == pytest.approx(72.23 * 0.2 * 4.0 * 0.5)  # days-left cap, off unless configured
    assert units_sold_at_discount(72.23, 0.2, ctx(markdown_ramp_days=10.0, days_left=30.0)) == pytest.approx(72.23 * 0.2 * 4.0)


def test_elasticity_per_category_with_default():
    assert ctx(elasticity_by_category={"snacks": 2.0}).elasticity() == 2.0
    assert ctx(elasticity_by_category={"beverages": 2.0}).elasticity() == 4.0  # falls back to the default
    low, high = ctx(elasticity_by_category={"snacks": 1.0}), ctx(elasticity_by_category={"snacks": 3.0})
    assert units_sold_at_discount(50, 0.2, low) < units_sold_at_discount(50, 0.2, high)
    tenant = load_tenant()
    assert tenant.elasticity_for("snacks") == 4.0 == tenant.thresholds["markdown_elasticity"]  # demo behaviour unchanged
    assert dataclasses.replace(tenant, elasticity={"snacks": 1.5}).elasticity_for("snacks") == 1.5


@pytest.mark.parametrize("mechanic,key,low,high", [("coupon", "discount_pct", 5, 25), ("outlet_markdown", "markdown_pct", 5, 25), ("markdown", "markdown_pct", 5, 25)])
def test_deeper_discount_never_sells_fewer_units(mechanic, key, low, high):
    c = ctx()
    units = [estimate(draw(mechanic, **{key: p}), c)["expected_outcome"]["units"] for p in range(low, high + 1, 5)]
    assert units == sorted(units) and units[-1] > units[0]


def test_deeper_bundle_never_sells_fewer_units():
    c = ctx(bundle_partner_unit_cost=20.0, bundle_partner_list_price=40.0)
    units = [estimate(draw("bundle", bundle_sku="P", bundle_price=70 - d), c)["expected_outcome"]["units"] for d in (0, 5, 10, 15)]
    assert units == sorted(units) and units[-1] > units[0]


def test_same_inputs_same_uplift_for_markdown_play_and_blanket_baseline():
    """The markdown play's units ARE the blanket baseline's uplift: one function, one answer."""
    c = ctx()
    for pct in (10, 20, 35):
        play = estimate(draw("markdown", markdown_pct=pct), c)
        uplift = units_sold_at_discount(72.23, pct / 100, c)
        assert play["expected_outcome"]["units"] == round(uplift, 2)
        cf = play["counterfactuals"]
        assert cf["blanket_markdown_pct"] == pct
        # blanket = discount given on the baseline volume + the lot still written off after that uplift
        assert cf["blanket_markdown_inr"] == round(72.23 * pct / 100 * 30.0 + max(0.0, 368 - uplift) * 25.0, 2)


def test_coupon_with_zero_depth_equals_the_old_rate_units_and_depth_adds_units():
    c = ctx()
    base = estimate(draw("coupon", discount_pct=0), c)["expected_outcome"]["units"]
    assert base == round(315 / 20, 2)
    assert estimate(draw("coupon", discount_pct=20), c)["expected_outcome"]["units"] > base


def test_golden_old_vs_new_targeted_play_and_unchanged_transfer():
    """est-v1 (recorded plays) vs est-v2: a 15% chips coupon sells 15.75 units under v1 and 15.75 * (1 + 4 * 0.15) =
    25.2 under v2; a transfer (no discount) is identical under both, so recordings of it still validate."""
    c = ctx()
    v1 = dataclasses.replace(c, estimator_version="est-v1")
    old = estimate(draw("coupon", discount_pct=15), v1)["expected_outcome"]
    new = estimate(draw("coupon", discount_pct=15), c)["expected_outcome"]
    assert old["units"] == 15.75 and new["units"] == 25.2
    assert old["estimator_version"] == "est-v1" and new["estimator_version"] == "est-v2"
    t_old = estimate(draw("transfer_plus_nudge", transfer_units=100), v1)
    t_new = estimate(draw("transfer_plus_nudge", transfer_units=100), c)
    for k in ("units", "margin_inr", "waste_avoided_inr", "discount_cost_inr", "ci_low", "ci_high"):
        assert t_old["expected_outcome"][k] == t_new["expected_outcome"][k]
    assert t_old["counterfactuals"] == t_new["counterfactuals"]


def test_counterfactuals_unchanged_by_the_refactor():
    c = ctx()
    cf = counterfactuals(draw("transfer_plus_nudge"), c)
    uplift = min(72.23 * 0.2 * 4.0, 368)
    assert cf["blanket_markdown_inr"] == round(72.23 * 0.2 * 30.0 + (368 - uplift) * 25.0, 2)


# ------------------------------------------------------------------ best markdown, beats_markdown

def test_best_markdown_respects_floor_and_depths():
    assert best_markdown(ctx(product=TEA, audience=0, units_at_risk=103, baseline=16.51))["markdown_pct"] == 10.0  # only 10% clears the 12% floor
    assert best_markdown(ctx(product=TEA, audience=0, units_at_risk=103, baseline=16.51), depths_pct=(35,)) is None
    assert best_markdown(ctx(product=TEA, audience=0, units_at_risk=103, baseline=16.51), depths_pct=(35,), floor_pct=-100.0)["markdown_pct"] == 35.0


def _gctx(tenant=None, product=WIDGET):
    return gr.GuardrailContext(product=product, tenant=tenant or load_tenant())


def _play(**over):
    d = {"objective": "clear_expiry", "mechanic": "coupon", "mechanic_params": {"discount_pct": 5}, "target": {"sku": CHIPS.sku, "node_ids": ["DS-07"], "deadline_type": "expiry", "deadline_date": "2026-09-20"},
         "audience": {"segment_ids": ["seg_1"], "purpose": "marketing", "size_before_consent": 100, "size_after_consent": 80}, "channel": "web_chat", "copy": {"copy_status": "pending", "variants": []},
         "holdout": {"fraction": 0.1, "seed": "seed-x", "min_treated_n": 20}, "rationale": "x", "citations": []}
    d.update(over)
    return d


def test_beats_markdown_rejects_a_play_far_below_the_markdown_and_names_it():
    c = ctx(product=WIDGET, audience=80)
    play = _play()
    est = estimate(play, c)
    out = gr.check_beats_markdown(play, est, _gctx(), c)
    assert not out["passed"] and "a markdown at 35% recovers INR" in out["detail"] and "propose it or a play that beats it" in out["detail"]
    assert out["best_markdown"]["markdown_pct"] == 35.0


def test_beats_markdown_passes_the_markdown_itself_and_respects_tolerance_config():
    c = ctx(product=WIDGET, audience=80)
    md = _play(mechanic="markdown", mechanic_params={"markdown_pct": 35})
    assert gr.check_beats_markdown(md, estimate(md, c), _gctx(), c)["passed"]
    weak = _play(mechanic="markdown", mechanic_params={"markdown_pct": 10})
    est = estimate(weak, c)
    gap = best_markdown(c)["recovery_inr"] - recovery_of(est)
    assert gap > 500 and not gr.check_beats_markdown(weak, est, _gctx(), c)["passed"]
    loose = dataclasses.replace(load_tenant(), raw={**load_tenant().raw, "markdown": {**load_tenant().raw["markdown"], "beats_tolerance_inr": gap + 1, "beats_tolerance_pct": 0}})
    assert gr.check_beats_markdown(weak, est, _gctx(loose), c)["passed"]
    assert gr.beats_markdown_tolerance(load_tenant(), 1000.0) == 500.0 and gr.beats_markdown_tolerance(load_tenant(), 100000.0) == 5000.0


def test_beats_markdown_is_skipped_past_online_sellby():
    c = ctx(product=WIDGET, audience=80)
    assert gr.check_beats_markdown(_play(), estimate(_play(), c), _gctx(), c, sellby_passed=True)["passed"]


# ------------------------------------------------------------------ guardrails for a markdown

def md_draft(**over):
    base = {"objective": "clear_online_sellby", "mechanic": "markdown", "mechanic_params": {"markdown_pct": 20, "end_date": "2026-09-20"},
            "target": {"sku": CHIPS.sku, "node_ids": ["DS-07"], "deadline_type": "online_sellby", "deadline_date": "2026-09-20"},
            "audience": {"segment_ids": ["all"], "purpose": "marketing", "size_before_consent": 0, "size_after_consent": 0}, "channel": "web_chat",
            "copy": {"copy_status": "pending", "variants": []}, "holdout": {"fraction": 0.5, "seed": "seed-x", "min_treated_n": 20, "measurement": "none", "measurement_reason": "only one node"},
            "rationale": "x", "citations": []}
    base.update(over)
    return base


def test_markdown_margin_floor_applies_and_clearance_exception_is_off_by_default():
    deep = md_draft(mechanic_params={"markdown_pct": 20})
    assert gr.rule_margin_floor(deep, _gctx(product=CHIPS))["passed"] is False  # 30 -> 24, cost 25
    assert gr.rule_margin_floor(md_draft(mechanic_params={"markdown_pct": 5}), _gctx(product=CHIPS))["passed"] is True
    from datetime import date

    base = load_tenant()
    on = dataclasses.replace(base, raw={**base.raw, "markdown": {**base.raw["markdown"], "clearance_window_days": 5, "clearance_margin_floor_pct": -50.0}})
    near = gr.GuardrailContext(product=CHIPS, tenant=on, as_of=date(2026, 9, 17))
    far = gr.GuardrailContext(product=CHIPS, tenant=on, as_of=date(2026, 9, 1))
    off = gr.GuardrailContext(product=CHIPS, tenant=base, as_of=date(2026, 9, 17))
    assert gr.rule_margin_floor(deep, near)["passed"] and "clearance floor" in gr.rule_margin_floor(deep, near)["detail"]
    assert not gr.rule_margin_floor(deep, far)["passed"] and not gr.rule_margin_floor(deep, off)["passed"]
    coupon = _play(mechanic_params={"discount_pct": 40})
    assert not gr.rule_margin_floor(coupon, near)["passed"]  # the exception is for the markdown mechanic only


def test_markdown_skips_frequency_consent_subscription_but_keeps_sellby_and_stockout():
    ctx_ = gr.GuardrailContext(product=CHIPS, audience_customer_ids=["c1"], recent_plays_count={"c1": 9}, subscribers_for_sku=frozenset({"c1"}), stockout_gap_skus_at_node=frozenset({CHIPS.sku}))
    d = md_draft()
    assert gr.rule_frequency_cap(d, ctx_)["passed"] and gr.rule_consent_required(d, ctx_)["passed"] and gr.rule_subscription_protect(d, ctx_)["passed"]
    assert "no customer is contacted" in gr.rule_consent_required(d, ctx_)["detail"]
    assert not gr.rule_no_cannibalise_stockout(d, ctx_)["passed"]
    no_disclosure = md_draft(copy={"copy_status": "generated", "variants": [{"segment_id": "all", "language": "en", "text": "x", "disclosure_included": False}]})
    assert not gr.rule_sellby_disclosure(no_disclosure, _gctx())["passed"]


def test_markdown_holdout_rule_node_holdout_or_stated_none():
    assert gr.rule_holdout_required(md_draft(), _gctx())["passed"]  # measurement none with a reason
    d = md_draft()
    d["holdout"] = {**d["holdout"], "measurement": "none", "measurement_reason": ""}
    assert not gr.rule_holdout_required(d, _gctx())["passed"]
    d["holdout"] = {**d["holdout"], "measurement": "holdout_nodes", "node_ids": ["DS-02"]}
    assert gr.rule_holdout_required(d, _gctx())["passed"] and "node holdout" in gr.rule_holdout_required(d, _gctx())["detail"]
    d["holdout"]["node_ids"] = ["DS-07"]  # the treated node cannot be its own control
    assert not gr.rule_holdout_required(d, _gctx())["passed"]
    d["holdout"] = {**d["holdout"], "measurement": None}
    assert not gr.rule_holdout_required(d, _gctx())["passed"]
    assert gr.rule_holdout_required(_play(), _gctx())["passed"]  # customer plays: as before


def test_eight_rules_stay_eight():
    from agents.gate.models import GUARDRAIL_RULES

    assert len(GUARDRAIL_RULES) == 8 and "beats_markdown" not in GUARDRAIL_RULES
    assert [r["rule"] for r in gr.check(md_draft(), _gctx())["results"]] == list(GUARDRAIL_RULES)


# ------------------------------------------------------------------ tools on the demo tenant

@pytest.fixture
def planner(data_dir):
    from agents.planner.context import PlannerContext, reset_context, set_context

    c = PlannerContext.build(data_dir, run_id="t")
    token = set_context(c)
    yield c
    reset_context(token)


def test_estimate_outcomes_returns_the_best_markdown_in_alternatives(planner):
    from agents.planner import drafting
    from agents.planner import tools as pt

    c = planner
    seen = []
    for gap_id in ("gap_chips_ds07", "gap_cola_ds07", "gap_cola_ds02", "gap_kaju_ds01", "gap_kaju_ds03", "gap_tea_ds04"):
        gap = pt.get_gap(gap_id)
        audiences = pt.get_candidate_audiences(gap["sku"], [gap["node_id"]], "clear_online_sellby")
        cand = drafting.candidate_mechanics(gap, c.policy_text)[0]
        draft = drafting.build_draft(gap, audiences, cand, c.policy_version, "t", 0.1, 20, ["en"], c.as_of.isoformat())
        out = pt.estimate_outcomes([draft])[0]
        alts = out.get("alternatives") or []
        if alts:
            assert alts[0]["mechanic"] == "markdown" and alts[0]["mechanic_params"]["markdown_pct"] in (10.0, 20.0, 35.0)
            assert "best_markdown_recovery_inr" in out and alts[0]["rejected_because"].startswith("reference only")
            seen.append(gap_id)
        else:  # no depth clears the margin floor, or the lot is past its online sell-by / at an outlet
            assert "best_markdown_recovery_inr" not in out
    assert seen, "at least one demo gap has an allowed markdown"


def test_markdown_draft_gets_server_owned_fields_and_node_measurement(planner):
    from agents.planner import tools as pt

    c = planner
    gap = pt.get_gap("gap_chips_ds07")
    draft = {"gap_id": "gap_chips_ds07", "objective": "clear_online_sellby", "mechanic": "markdown", "mechanic_params": {"markdown_pct": 10}, "target": {"sku": gap["sku"], "node_ids": ["DS-01", "DS-02"], "batch_ids": [], "units": 1, "deadline_date": gap["deadline_date"], "deadline_type": gap["deadline_type"]},
             "holdout": {"fraction": 0.1, "seed": "seed-play_md1", "min_treated_n": 20}}
    out = pt.estimate_outcomes([draft])[0]
    assert "error" not in out and out["audience"] == {"size_before_consent": 0, "size_after_consent": 0}
    d = json.loads(json.dumps(draft))
    pt.apply_derived_audience(c, d)
    assert d["target"]["node_ids"] == [gap["node_id"]] and d["mechanic_params"]["end_date"] == gap["deadline_date"]
    h = d["holdout"]
    if pt.comparable_at_risk_nodes(c, gap):
        assert h["measurement"] == "holdout_nodes" and h["node_ids"] and gap["node_id"] not in h["node_ids"]
    else:
        assert h["measurement"] == "none" and "cannot be measured against a holdout" in h["measurement_reason"]
    assert pt.apply_derived_audience(c, d) is None  # idempotent shape
    bad = pt.estimate_outcomes([{**draft, "mechanic_params": {}}])[0]
    assert "markdown_pct" in bad["error"]


# ------------------------------------------------------------------ the hero Tea play does not move

def test_tea_hero_play_is_unchanged(base_store):
    """Tea: transfer_plus_nudge, margin INR 9,191.29, 355 treated / 39 holdout. A transfer has no discount, so the
    est-v2 demand model leaves it alone: re-estimating the recorded play under est-v2 reproduces its figures, and
    the beats_markdown check does not reject it (the best allowed markdown recovers far less)."""
    from agents.planner import tools as pt
    from agents.planner.context import PlannerContext, reset_context, set_context

    row = base_store.find("plays", play_id="play_tea_ds04_v1")[-1]
    play = json.loads(row["play_json"])
    assert play["mechanic"] == "transfer_plus_nudge"
    assert play["expected_outcome"]["margin_inr"] == 9191.29
    assert play["audience"]["size_after_consent"] == 394
    arms = assign(play, [f"c{i}" for i in range(0)], assigned_at="x")
    assert arms == []  # customer ids come from the tools; the real arm counts are asserted from the recorded play below
    c = PlannerContext.build(base_store.root, run_id="tea")
    token = set_context(c)
    try:
        ectx = pt._estimator_context(c, play)
        assert ectx.estimator_version == "est-v2"
        est = estimate(play, ectx)
        for k in ("units", "margin_inr", "waste_avoided_inr", "discount_cost_inr", "ci_low", "ci_high"):
            assert est["expected_outcome"][k] == play["expected_outcome"][k], k
        assert est["counterfactuals"]["do_nothing_inr"] == play["counterfactuals"]["do_nothing_inr"]
        assert est["counterfactuals"]["blanket_markdown_inr"] == play["counterfactuals"]["blanket_markdown_inr"]
        assert est["counterfactuals"]["play_net_inr"] == play["counterfactuals"]["play_net_inr"]
        gctx = pt._guardrail_context(c, play)
        bm = gr.check_beats_markdown(play, est, gctx, ectx)
        assert bm["passed"], bm["detail"]
        ids, eligible = pt.eligible_audience(c, play)
        rows = assign(play, eligible, assigned_at="2026-09-12T03:30:00Z")
        assert (sum(r["arm"] == "treated" for r in rows), sum(r["arm"] == "holdout" for r in rows)) == (355, 39)
    finally:
        reset_context(token)


def test_tenant_config_loads_new_tables():
    t = load_tenant()
    assert isinstance(t, TenantConfig) and t.markdown_setting("depths_pct", None) == [10, 20, 35]
    assert t.markdown_setting("clearance_window_days", None) == 0  # clearance exception off by default


# ------------------------------------------------------------------ end to end: propose and approve a markdown

def _markdown_gap(c):
    from agents.planner import tools as pt

    for g in c.store.read("gaps"):
        if g["type"] not in ("online_sellby_breach", "expiry_writeoff") or float(g["rupees_at_stake"]) < 500:
            continue
        draft = {"gap_id": g["gap_id"], "objective": "clear_online_sellby" if g["type"] == "online_sellby_breach" else "clear_expiry", "mechanic": "markdown", "mechanic_params": {"markdown_pct": 10},
                 "target": {"sku": g["sku"], "node_ids": [g["node_id"]], "batch_ids": [], "units": 1, "deadline_date": g["deadline_date"], "deadline_type": g["deadline_type"]}}
        ref = pt._markdown_reference(c, draft)
        if ref:
            return g, ref["alternatives"][0]["mechanic_params"]["markdown_pct"]
    raise AssertionError("no gap with an allowed markdown in the demo tenant")


def test_markdown_play_is_proposed_and_approved_without_contacting_anyone(data_dir, sandbox):
    from datetime import UTC, datetime
    from types import SimpleNamespace

    from agents.planner import drafting
    from agents.planner import tools as pt
    from agents.planner.context import PlannerContext, reset_context, set_context
    from services.api.approve import approve

    for t in ("gaps", "plays", "products", "nodes", "customers", "affinity", "consent", "segments", "estimator_priors", "play_assignments", "inventory_batches", "inbound", "order_lines", "play_outcomes", "sense_runs", "policy", "offers", "future_regressors", "forecasts", "approvals"):
        try:
            sandbox._materialise(t)
        except Exception:  # a table the tenant does not have
            pass
    if not (sandbox.root / "manifest.json").exists():
        (sandbox.root / "manifest.json").write_bytes((data_dir / "manifest.json").read_bytes())
    c = PlannerContext.build(sandbox.root, run_id="md")
    token = set_context(c)
    try:
        g, pct = _markdown_gap(c)
        gap = pt.get_gap(g["gap_id"])
        audiences = pt.get_candidate_audiences(gap["sku"], [gap["node_id"]], "clear_expiry")
        cand = {"mechanic": "markdown", "mechanic_params": {"markdown_pct": pct}}
        draft = drafting.build_draft(gap, audiences, cand, c.policy_version, "md", 0.1, 20, ["en", "kn"], c.as_of.isoformat())
        est = pt.estimate_outcomes([draft])[0]
        play = drafting.finish_draft(draft, gap, est, audiences, [], c.policy_text)
        tc = SimpleNamespace(state={}, actions=SimpleNamespace(escalate=False))
        res = pt.propose_play(play, tc)
        assert res["valid"], res["errors"]
        stored = json.loads(c.store.find("plays", play_id=res["play_id"])[-1]["play_json"])
        assert stored["mechanic"] == "markdown" and stored["mechanic_params"]["end_date"] == g["deadline_date"]
        assert stored["audience"]["size_after_consent"] == 0 and len(stored["guardrails"]) == 8 and all(r["passed"] for r in stored["guardrails"])
        assert stored["holdout"]["measurement"] in ("holdout_nodes", "none") and stored["holdout"]["measurement_reason"]
        out = approve(sandbox, c.tenant, res["play_id"], datetime(2026, 9, 12, 3, 30, tzinfo=UTC))
        assert out["assignment"]["treated_n"] == 0 and out["offers_written"] == 0
        assert out["copy"]["variants"] >= 1 and not out["copy"]["rejected"], out["copy"]
    finally:
        reset_context(token)


# ------------------------------------------------------------------ v3 changes

def test_play_below_the_blanket_20_figure_is_rejected_when_20_is_legal():
    """On a product whose margin lets a 20% cut clear the floor, a play that recovers less than the blanket 20% figure
    (do_nothing - blanket_markdown) is rejected by beats_markdown: the `markdown` mechanic at 20% always recovers at least
    that figure (it also counts the margin on the extra units), so the best allowed markdown is never below it."""
    c = ctx(product=WIDGET, audience=80)
    play = _play()
    est = estimate(play, c)
    cf = est["counterfactuals"]
    blanket20 = round(cf["do_nothing_inr"] - cf["blanket_markdown_inr"], 2)
    assert cf["blanket_markdown_pct"] == 20.0 and recovery_of(est) < blanket20
    out = gr.check_beats_markdown(play, est, _gctx(), c)
    assert not out["passed"] and out["best_markdown"]["recovery_inr"] >= blanket20
    # where 20% is NOT legal (a thin margin) no legal play can be held to it: the check compares with the legal depths only
    thin = ctx(product=CHIPS, audience=80)
    assert gr.check_beats_markdown(_play(), estimate(_play(), thin), _gctx(product=CHIPS), thin)["best_markdown"] is None


def test_estimate_outcomes_states_the_markdown_reference_once(planner):
    from agents.planner import drafting
    from agents.planner import tools as pt

    c = planner
    for gap_id in ("gap_tea_ds04", "gap_cola_ds07", "gap_kaju_ds01"):
        gap = pt.get_gap(gap_id)
        audiences = pt.get_candidate_audiences(gap["sku"], [gap["node_id"]], "clear_expiry")
        drafts = [drafting.build_draft(gap, audiences, cand, c.policy_version, "t", 0.1, 20, ["en"], c.as_of.isoformat()) for cand in drafting.candidate_mechanics(gap, c.policy_text)[:3]]
        if len(drafts) < 2:
            continue
        out = pt.estimate_outcomes(drafts)
        assert all("alternatives" not in r for r in out[1:])
        assert all("best_markdown_recovery_inr" not in r for r in out[1:])
        return
    raise AssertionError("no gap with 2+ candidates")


def test_retry_on_429_is_off_by_default_and_the_harness_pregenerates_tenants():
    import harness.adversarial_eval as ae
    import harness.sealed_eval as se

    assert ae.RETRY_429 == 0  # the adversarial harness and the v1/v2 sealed runs keep their behaviour
    src = open(se.__file__, encoding="utf-8").read()
    assert "default=3" in src and "--retry-429" in src and "ensure_tenant(Path(args.data_root), seed)" in src
