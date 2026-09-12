"""Rolling-origin backtest (DECISIONS §5.2 step 8, §12): the only way to know a forecast is any
good is to have refit it on the past and checked it against what actually happened."""
from datetime import date, timedelta

from jobs.sense.backtest import HORIZON, MAX_ORIGINS, _origins, run_backtest


def test_origins_step_back_weekly_with_a_real_lead_in_and_validation_window():
    all_dates = {date(2026, 7, 1) + timedelta(days=i) for i in range(70)}
    origins = _origins(all_dates, HORIZON)
    assert 1 <= len(origins) <= MAX_ORIGINS
    last_actual = max(all_dates)
    first_actual = min(all_dates)
    for o in origins:
        assert o + timedelta(days=HORIZON) <= last_actual, "needs real actuals to validate against"
        assert o - timedelta(days=14) >= first_actual, "needs a real lead-in to fit on"
    # weekly cadence
    diffs = {(origins[i] - origins[i + 1]).days for i in range(len(origins) - 1)}
    assert diffs <= {7}


def test_origins_empty_on_no_data():
    assert _origins(set(), HORIZON) == []


def test_run_backtest_writes_mape_bias_and_n_series_per_tier_and_model(sandbox):
    rows = run_backtest(sandbox, "test-backtest", "2026-09-12T00:00:00Z")
    assert rows, "the demo tenant's 70-day sample slice must yield at least one origin"
    for r in rows:
        assert r["mape"] is None or r["mape"] >= 0
        assert r["n_series"] > 0
        assert r["tier"] and r["model"]
    written = [r for r in sandbox.read("eval_forecast") if r["run_id"] == "test-backtest"]
    assert len(written) == len(rows)
    # a real accuracy check, not just plumbing: the seasonal-naive model on clean synthetic
    # data should not be wildly wrong
    mapes = [r["mape"] for r in rows if r["mape"] is not None]
    assert mapes and sum(mapes) / len(mapes) < 0.5


def test_run_backtest_is_additive_across_runs(sandbox):
    before = len(sandbox.read("eval_forecast"))
    run_backtest(sandbox, "test-backtest-a", "2026-09-12T00:00:00Z")
    run_backtest(sandbox, "test-backtest-b", "2026-09-12T00:00:00Z")
    after = sandbox.read("eval_forecast")
    assert len(after) > before
    assert {r["run_id"] for r in after} >= {"test-backtest-a", "test-backtest-b"}
