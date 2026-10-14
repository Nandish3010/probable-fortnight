"""Fair-metrics backtest pieces against hand-computed values on tiny synthetic series: Croston, SBA,
the zero-filled candidates, MASE scaling, all-days / sale-day / weekly scoring, the no-look-ahead
guarantee for every method, and that the committed v2 numbers reproduce from the committed sample."""
from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from harness.external_backtest import (
    PROTOCOL,
    croston_state,
    ew_level,
    f_croston,
    f_mean28,
    f_median28,
    f_sba,
    f_v1,
    f_v2,
    f_v3,
    f_v4,
    group_metrics,
    horizon_days,
    mase_pair,
    mase_scale,
    method_functions,
    run_fair,
    zero_filled_dow,
)

ROOT = Path(__file__).resolve().parents[2]
SAMPLE = ROOT / "data" / "external" / "online_retail_ii" / "sample"
ORIGIN = date(2026, 3, 30)  # a Monday


def hist_from(units: dict[date, float]) -> dict[date, tuple[float, bool]]:
    return {d: (u, False) for d, u in units.items()}


def test_croston_by_hand():
    # demands on day 0 (10), day 2 (20), day 3 (10); alpha 0.5; z0 = 10, p0 = 1
    # day 2: q = 2 -> z = 10 + .5 (20 - 10) = 15, p = 1 + .5 (2 - 1) = 1.5
    # day 3: q = 1 -> z = 15 + .5 (10 - 15) = 12.5, p = 1.5 + .5 (1 - 1.5) = 1.25
    d0 = ORIGIN - timedelta(days=10)
    units = {d0: 10.0, d0 + timedelta(days=2): 20.0, d0 + timedelta(days=3): 10.0}
    z, p = croston_state(units, ORIGIN, 0.5)
    assert (z, p) == (12.5, 1.25)
    assert f_croston(hist_from(units), ORIGIN, 0.5) == [10.0] * 7            # 12.5 / 1.25
    assert f_sba(hist_from(units), ORIGIN, 0.5) == [7.5] * 7                 # (1 - .25) * 10
    assert croston_state({}, ORIGIN, 0.5) == (0.0, 1.0) and f_croston({}, ORIGIN) == [0.0] * 7


def test_croston_ignores_zero_days_and_the_future():
    d0 = ORIGIN - timedelta(days=5)
    units = {d0: 4.0, d0 + timedelta(days=1): 0.0, ORIGIN: 99.0, ORIGIN + timedelta(days=2): 99.0}
    assert croston_state(units, ORIGIN, 0.3) == (4.0, 1.0)                   # one demand before ORIGIN, zero-unit row skipped


def test_mean_and_median_are_28_zero_filled_days():
    units = {ORIGIN - timedelta(days=1): 28.0, ORIGIN - timedelta(days=10): 14.0, ORIGIN - timedelta(days=28): 28.0,
             ORIGIN - timedelta(days=29): 1000.0}                            # day 29 is outside the window
    assert f_mean28(hist_from(units), ORIGIN) == [70.0 / 28] * 7
    assert f_median28(hist_from(units), ORIGIN) == [0.0] * 7                 # 25 of 28 days are zero
    full = {ORIGIN - timedelta(days=j): 2.0 for j in range(1, 29)}
    full[ORIGIN - timedelta(days=1)] = 30.0
    assert f_median28(hist_from(full), ORIGIN) == [2.0] * 7


def test_zero_filled_dow_counts_days_without_a_sale():
    # 91 window days = 13 of each weekday. Sales only on Mondays (13 of them, 7 units each): mean 1/day.
    units = {ORIGIN - timedelta(days=7 * k): 7.0 for k in range(1, 14)}      # O is a Monday
    w = zero_filled_dow(units, ORIGIN)
    assert w[0] == pytest.approx(7.0) and w[1:] == [0.0] * 6
    assert zero_filled_dow({}, ORIGIN) == [1.0] * 7


def test_v4_by_hand():
    units = {ORIGIN - timedelta(days=7 * k): 7.0 for k in range(1, 14)}      # level 4 * 7 / 28 = 1 ; w = [7, 0 x 6]
    v4 = f_v4(hist_from(units), ORIGIN)
    assert v4 == [4.0] + [0.5] * 6                                      # Mon: 1 * (.5 * 7 + .5) ; other days: 1 * .5


def test_ew_level_by_hand():
    # window 3, half-life 1: weights for ages 0, 1, 2 = 1, .5, .25 ; units 8 (age 0), 0 (age 1), 4 (age 2)
    units = {ORIGIN - timedelta(days=1): 8.0, ORIGIN - timedelta(days=3): 4.0}
    assert ew_level(units, ORIGIN, window=3, half_life=1) == pytest.approx((8 * 1 + 0 * 0.5 + 4 * 0.25) / 1.75)


def test_v1_v2_v3_by_hand_on_a_dense_series():
    # 28 dense days: Mondays 4 units, others 2. mean_all = 64 / 28 ; Monday raw dow 1.75 -> .7 * 1.75 + .3 = 1.525
    units = {ORIGIN - timedelta(days=j): (4.0 if (ORIGIN - timedelta(days=j)).weekday() == 0 else 2.0) for j in range(1, 29)}
    level = 64 / 28
    h = hist_from(units)
    assert f_v1(h, ORIGIN)[0] == pytest.approx(level * 1.525)                # O is a Monday
    assert f_v2(h, ORIGIN)[0] == pytest.approx(0.5 * level * 1.525 + 0.5 * level)
    assert f_v3(h, ORIGIN)[0] == pytest.approx(level * (0.5 * 1.525 + 0.5))
    tue = 0.7 * (2 / level) + 0.3                                       # Tuesday's multiplier
    assert f_v1(h, ORIGIN)[1] == pytest.approx(level * tue)


def test_v1_uses_zero_filled_level_not_sale_day_level():
    # 7 sale days of 4 units in the last 28 days: a sale-day level would be 4, the zero-filled level is 1.
    units = {ORIGIN - timedelta(days=j): 4.0 for j in range(1, 8)}
    assert f_v1(hist_from(units), ORIGIN) == [1.0] * 7                       # intermittent -> flat weekday shape -> level only


def test_mase_scale_and_pair_by_hand():
    # sales: O-1: 7, O-8: 3, O-15: 3. Terms |y(d) - y(d-7)| for d in [O-28, O-1]:
    #   d = O-1: |7 - 3| = 4 ; d = O-8: |3 - 3| = 0 ; d = O-15: |3 - 0| = 3 ; every other d: 0.  Sum 7, / 28 = 0.25
    units = {ORIGIN - timedelta(days=1): 7.0, ORIGIN - timedelta(days=8): 3.0, ORIGIN - timedelta(days=15): 3.0, ORIGIN: 500.0}
    assert mase_scale(units, ORIGIN) == 0.25
    assert mase_scale({}, ORIGIN) == 0.0
    # forecast flat 1 against actual [2, 0 x 6]: MAE = (1 + 6) / 7 = 1 ; MASE = 1 / .25 = 4
    assert mase_pair([1.0] * 7, [2.0, 0, 0, 0, 0, 0, 0], 0.25) == 4.0


def pair(origin, actual, f, fast=False, scale=1.0):
    return {"origin": origin, "actual": actual, "fast": fast, "scale": scale, "preds": {"m": f}}


def test_all_days_sale_day_weekly_bias_by_hand():
    p1 = pair(ORIGIN, [2.0, 0, 0, 0, 0, 0, 4.0], [1.0] * 7)                  # abs errors 1,1,1,1,1,1,3 = 9 ; A = 6 ; F = 7
    p2 = pair(ORIGIN, [5.0, 0, 0, 0, 0, 0, 0], [2.0] * 7, scale=0.0)         # abs errors 3 + 6*2 = 15 ; A = 5 ; F = 14
    p3 = pair(ORIGIN, [0.0] * 7, [3.0] * 7)                                  # no sale in the window: excluded from all-days / weekly
    m = group_metrics([p1, p2, p3], "m")
    assert m["n_pairs"] == 3 and m["n_pairs_scored_all_days"] == 2
    assert m["all_days_wape"] == round(24 / 11, 4)
    assert m["all_days_wape_no_exclusion"] == round(45 / 11, 4)         # sensitivity: p3 adds 21 of error and no actuals
    assert m["sale_day_wape"] == round(7 / 11, 4)                       # slots with a > 0: err 1, 3, 3 over actual 2 + 4 + 5
    assert m["weekly_wape"] == round(10 / 11, 4)                        # |7 - 6| + |14 - 5| = 10
    assert m["bias_all_days"] == round(10 / 11, 4)                      # (7 + 14 - 11) / 11
    assert m["bias_sale_days"] == round(-7 / 11, 4)                     # slot errors f - a: -1, -3, -3
    assert m["mase_mean"] == round((9 / 7 + 3) / 2, 4)                  # p2 excluded (scale 0); p1 MAE 9/7, p3 MAE 3
    assert m["mape_continuity_only"] == round((0.5 + 0.75 + 0.6) / 3, 4)  # one origin: APEs 1/2, 3/4, 3/5


def test_fast_mover_slice_and_origin_filter():
    o2 = ORIGIN + timedelta(days=7)
    p1 = pair(ORIGIN, [2.0] * 7, [1.0] * 7, fast=True)
    p2 = pair(ORIGIN, [2.0] * 7, [3.0] * 7, fast=False)
    p3 = pair(o2, [4.0] * 7, [4.0] * 7, fast=True)
    assert group_metrics([p1, p2, p3], "m", {ORIGIN}, fast_only=True)["all_days_wape"] == 0.5
    assert group_metrics([p1, p2, p3], "m", {ORIGIN})["all_days_wape"] == 0.5     # (7 + 7) / 28
    assert group_metrics([p1, p2, p3], "m", {o2})["all_days_wape"] == 0.0
    assert group_metrics([p1, p2, p3], "m")["n_pairs"] == 3


def test_no_method_reads_rows_at_or_after_the_origin():
    base = {ORIGIN - timedelta(days=j): (float(j % 5 + 1), False) for j in range(1, 120) if j % 3}
    poisoned = dict(base)
    for k in (0, 1, 3, 6, 7, 14):
        poisoned[ORIGIN + timedelta(days=k)] = (123456.0, True)
    for name, fn in method_functions().items():
        assert fn(poisoned, ORIGIN) == fn(base, ORIGIN), name
        assert len(fn(base, ORIGIN)) == len(horizon_days(ORIGIN)) == 7


def test_methods_are_deterministic():
    base = {ORIGIN - timedelta(days=j): (float(j % 5 + 1), False) for j in range(1, 60)}
    for name, fn in method_functions().items():
        assert fn(base, ORIGIN) == fn(base, ORIGIN), name


def test_committed_v2_numbers_reproduce_and_the_protocol_hash_matches():
    committed = json.loads((ROOT / "eval" / "raw" / "external_backtest_v2_2026-10-14.json").read_text())
    assert committed["protocol"]["sha256"] == hashlib.sha256(PROTOCOL.read_bytes()).hexdigest()
    now = run_fair(SAMPLE)
    for k in ("results", "decision_rule", "chosen_alpha", "alpha_grid_all_days_wape", "per_origin_all_days_wape", "diagnostics", "post_hoc_diagnostics", "inputs"):
        assert json.loads(json.dumps(now[k])) == committed[k], k


def test_v2_all_origin_taal_row_reproduces_the_earlier_report():
    committed = json.loads((ROOT / "eval" / "raw" / "external_backtest_v2_2026-10-14.json").read_text())
    taal = committed["results"]["ALL"]["all"]["methods"]["taal"]
    assert taal["n_sale_day_slots"] == 10809
    assert round(taal["sale_day_wape"], 3) == 0.826
    assert round(taal["mape_continuity_only"], 3) == 3.786
    assert committed["shipped_forecaster_changed"] is False
