"""The gate re-derives audience, channel and estimate figures; Approve splits that same audience."""
import copy
import json
from datetime import UTC, datetime

from agents.gate.config import load_tenant
from agents.planner import tools as pt
from agents.planner.context import PlannerContext, reset_context, set_context
from services.api.approve import approve

PLAY = "play_chips_ds07_v1"


def _play(store):
    return json.loads(store.find("plays", play_id=PLAY)[-1]["play_json"])


def _ctx(data_dir, store):
    ctx = PlannerContext.build(data_dir, run_id="t", policy_version=_play(store)["policy_version"])
    return ctx, set_context(ctx)


def test_gate_overwrites_model_stated_audience_channel_and_estimate(data_dir, sandbox):
    ctx, tok = _ctx(data_dir, sandbox)
    try:
        good = _play(sandbox)
        lie = copy.deepcopy(good)
        lie["channel"] = "outlet"
        lie["audience"]["size_after_consent"] = 334
        lie["audience"]["size_before_consent"] = 476
        lie["expected_outcome"]["units"] = 999.0
        lie["counterfactuals"]["do_nothing_inr"] = 1.0
        pt.rederive_play(ctx, lie)
        assert lie["channel"] == "web_chat"
        assert lie["audience"] == good["audience"]
        assert lie["expected_outcome"] == good["expected_outcome"]
        assert lie["counterfactuals"] == good["counterfactuals"]
    finally:
        reset_context(tok)


def test_personal_mechanics_are_never_outlet_channel():
    assert pt.derive_channel({"mechanic": "bundle"}) == "web_chat"
    assert pt.derive_channel({"mechanic": "transfer_plus_nudge"}) == "web_chat"
    assert pt.derive_channel({"mechanic": "outlet_markdown"}) == "outlet"


def test_guardrails_see_real_customers_even_if_model_says_outlet(data_dir, sandbox):
    ctx, tok = _ctx(data_dir, sandbox)
    try:
        lie = copy.deepcopy(_play(sandbox))
        lie["channel"] = "outlet"
        lie["audience"]["size_after_consent"] = 334
        res = pt.check_guardrails(lie)
        by = {r["rule"]: r for r in res["results"]}
        n = _play(sandbox)["audience"]["size_after_consent"]
        assert f"all {n} customers" in by["frequency_cap"]["detail"]
        assert "all 0" not in by["frequency_cap"]["detail"]
        assert by["consent_required"]["detail"].endswith(f"-> {n}")
    finally:
        reset_context(tok)


def test_estimate_outcomes_reports_the_derived_audience(data_dir, sandbox):
    ctx, tok = _ctx(data_dir, sandbox)
    try:
        lie = copy.deepcopy(_play(sandbox))
        lie["audience"]["size_after_consent"] = 334
        out = pt.estimate_outcomes([lie])[0]
        assert out["audience"]["size_after_consent"] == _play(sandbox)["audience"]["size_after_consent"]
    finally:
        reset_context(tok)


def test_approve_split_equals_gate_audience(sandbox):
    n = _play(sandbox)["audience"]["size_after_consent"]
    resp = approve(sandbox, load_tenant(), PLAY, datetime(2026, 9, 12, 9, 0, tzinfo=UTC))
    a = resp["assignment"]
    assert a["treated_n"] + a["holdout_n"] == a["eligible_n"] == n
