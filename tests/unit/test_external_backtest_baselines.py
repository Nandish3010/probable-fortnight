"""Seasonal-naive and trailing-28-day-mean baselines against hand-computed values on a tiny series,
and the committed baseline numbers reproduce from the committed sample (deterministic, no network)."""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from harness.external_backtest import (
    run_baselines,
    score,
    seasonal_naive,
    trailing_mean,
    trailing_mean_sale_days,
)

ROOT = Path(__file__).resolve().parents[2]
SAMPLE = ROOT / "data" / "external" / "online_retail_ii" / "sample"

ORIGIN = date(2026, 3, 30)  # a Monday
# Days before the origin with a sale (everything else is a no-sale day = 0):
#   Mar 23 (Mon, origin - 7) 10 units, Mar 24 (Tue) 4, Mar 26 (Thu) 6, Mar 2 (Mon, origin - 28) 28,
#   Mar 1 (origin - 29, outside the 28-day window) 1000
SERIES = {date(2026, 3, 23): 10.0, date(2026, 3, 24): 4.0, date(2026, 3, 26): 6.0,
          date(2026, 3, 2): 28.0, date(2026, 3, 1): 1000.0,
          date(2026, 3, 30): 999.0, date(2026, 4, 1): 999.0}  # origin and later: must never be read


def test_seasonal_naive_is_same_weekday_last_week():
    assert seasonal_naive(SERIES, ORIGIN, ORIGIN) == 10.0                        # Mon -> Mon 23 Mar
    assert seasonal_naive(SERIES, ORIGIN + timedelta(days=1), ORIGIN) == 4.0     # Tue -> Tue 24 Mar
    assert seasonal_naive(SERIES, ORIGIN + timedelta(days=3), ORIGIN) == 6.0     # Thu -> Thu 26 Mar
    assert seasonal_naive(SERIES, ORIGIN + timedelta(days=2), ORIGIN) == 0.0     # Wed: no sale last Wed


def test_seasonal_naive_never_reads_the_horizon():
    # Wed 1 Apr has 999 in SERIES but is not d - 7 for any horizon day; d = Apr 5 (Sun) -> Mar 29
    assert seasonal_naive(SERIES, date(2026, 4, 5), ORIGIN) == 0.0
    # a day beyond the horizon steps back whole weeks until strictly before the origin
    assert seasonal_naive(SERIES, date(2026, 4, 6), ORIGIN) == 10.0              # Mon 6 Apr -> Mar 23, not Mar 30


def test_trailing_mean_is_28_calendar_days_before_origin():
    # window = Mar 2 .. Mar 29 inclusive: 28 + 10 + 4 + 6 = 48 units over 28 days; Mar 1 and Mar 30+ excluded
    assert trailing_mean(SERIES, ORIGIN) == 48.0 / 28
    assert trailing_mean({}, ORIGIN) == 0.0


def test_sale_days_only_variant():
    # 4 days with a sale in the window: (28 + 10 + 4 + 6) / 4
    assert trailing_mean_sale_days(SERIES, ORIGIN) == 12.0
    assert trailing_mean_sale_days({}, ORIGIN) == 0.0


def test_score_wape_and_ape():
    # (actual, forecast): (10, 5) -> err 5; (20, 30) -> err 10; WAPE = 15 / 30; APEs 0.5 and 0.5
    r = score([(10.0, 5.0), (20.0, 30.0)])
    assert r["wape"] == 0.5 and r["mean_ape_pooled"] == 0.5


def test_committed_baseline_numbers_reproduce():
    committed = json.loads(max((ROOT / "eval" / "raw").glob("external_backtest_baselines_*.json")).read_text())
    now = run_baselines(SAMPLE)
    assert now["results"] == committed["results"]
    assert now["exclusions"] == committed["exclusions"]
    assert now["inputs"]["sample_sha256"] == committed["inputs"]["sample_sha256"]
    # same slots as the existing report: Taal's WAPE and scored series-days match it
    base = json.loads(max((ROOT / "eval" / "raw").glob("external_backtest_2026-*.json")).read_text())
    assert now["results"]["taal"]["scored_series_days"] == base["spread_behind_the_mean"]["scored_series_days"]
    assert round(now["results"]["taal"]["wape"], 2) == round(base["wape"], 2)
