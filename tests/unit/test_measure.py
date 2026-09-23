import pytest

from jobs.measure.run import (
    EMISSIONS_FACTOR_KGCO2E_PER_KG,
    MeasureError,
    measure_play,
    wilson_interval,
)

PRODUCT = {"tenant_id": "t", "sku": "S", "unit_cost": 25.0, "list_price": 30.0, "pack_weight_g": 200}


def play(min_treated=20):
    return {"play_id": "play_t", "tenant_id": "t", "target": {"sku": "S", "node_ids": ["DS-07"], "units": 100}, "window": {"start": "2026-09-12T00:00:00Z", "end": "2026-09-18T23:59:59Z"}, "holdout": {"min_treated_n": min_treated, "seed": "s", "fraction": 0.5}}


def arms(n_t, n_h):
    return [{"play_id": "play_t", "customer_id": f"T{i}", "arm": "treated"} for i in range(n_t)] + [{"play_id": "play_t", "customer_id": f"H{i}", "arm": "holdout"} for i in range(n_h)]


def line(cid, qty=1, disc=3.0, play_id="play_t", ts="2026-09-13T10:00:00Z", sku="S"):
    return {"customer_id": cid, "sku": sku, "node_id": "DS-07", "qty": qty, "price": 30.0, "discount": disc, "play_id": play_id, "ts": ts}


def test_known_outcome_reproduces_lift_and_ci():
    lines = [line(f"T{i}") for i in range(12)] + [line(f"H{i}", disc=0.0, play_id=None) for i in range(4)]
    rows = measure_play(play(), arms(100, 100), lines, PRODUCT, "2026-09-19T00:00:00Z")
    t, h = rows
    assert t["status"] == "measured" and t["responders"] == 12 and h["responders"] == 4
    assert t["lift"] == pytest.approx(0.12 - 0.04, abs=1e-6)
    # Wilson score interval per arm, differenced -- not the normal approximation, which is
    # degenerate at p=0 and can leave [0, 1]. See wilson_interval()/lift_wilson_interval().
    lo_t, hi_t = wilson_interval(12, 100)
    lo_h, hi_h = wilson_interval(4, 100)
    assert t["ci_low"] == pytest.approx(lo_t - hi_h, abs=1e-6)
    assert t["ci_high"] == pytest.approx(hi_t - lo_h, abs=1e-6)
    assert t["units_target_lot"] == 12 and t["discount_cost"] == 36.0 and t["margin"] == pytest.approx(12 * 2.0)
    assert t["waste_kg_est"] == pytest.approx(12 * 0.2) and t["co2e_kg_est"] == pytest.approx(12 * 0.2 * EMISSIONS_FACTOR_KGCO2E_PER_KG)
    assert t["net_margin_per_discount_inr"] == pytest.approx((24.0 - 20.0) / 36.0, abs=1e-4)


def test_below_min_treated_is_unmeasured_without_lift():
    rows = measure_play(play(min_treated=20), arms(10, 10), [line("T1")], PRODUCT, "x")
    assert rows[0]["status"] == "unmeasured" and rows[0]["lift"] is None and rows[0]["ci_low"] is None


def test_no_holdout_fails_the_job():
    with pytest.raises(MeasureError):
        measure_play(play(), arms(30, 0), [], PRODUCT, "x")


def test_orders_outside_window_or_other_sku_ignored():
    lines = [line("T1", ts="2026-09-20T00:00:00Z"), line("T2", sku="OTHER", play_id=None)]
    rows = measure_play(play(), arms(30, 10), lines, PRODUCT, "x")
    assert rows[0]["responders"] == 0


def test_zero_responders_refuses_instead_of_a_degenerate_zero_interval():
    """Both arms above min_treated_n but nobody actually responded: the normal approximation
    used to compute se=0 exactly and emit ci_low=ci_high=0.0, which reads as "measured, zero
    effect, dead certain" rather than "no evidence yet". Below MIN_SAMPLE_N total responders,
    refuse -- unmeasured, no lift, no CI."""
    rows = measure_play(play(min_treated=20), arms(30, 10), [], PRODUCT, "x")
    t = rows[0]
    assert t["responders"] == 0
    assert t["status"] == "unmeasured"
    assert t["lift"] is None and t["ci_low"] is None and t["ci_high"] is None
