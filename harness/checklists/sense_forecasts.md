---
component: sense_forecasts
title: "Sense: forecasts"
owner: D
spec_sections: ["5.2", "4.2"]
tests: ["tests/sql/test_forecast.py", "tests/sql/test_backtest.py"]
---
# Sense: forecasts (`jobs/sense`, `data/bigquery`)

## Deterministic (CI gate)
- [x] Backtest job runs on the sample slice (rolling origin, 8 weeks) — `jobs/sense/backtest.py` (`make backtest`); origins step back 7 days at a time, capped at 8, each needing a real 14-day lead-in and a real 7-day validation window of already-observed actuals. The demo tenant's 70-day sample slice supports 7 origins, not a full 8 -- `tests/sql/test_backtest.py` asserts the spacing and bounds rather than a hardcoded count, since forcing exactly 8 would mean starving the lead-in
- [x] MAPE and bias per tier and model computed and written to `eval_forecast` — `tier` is product category (a cluster mixes node types, so node type isn't a property of a (sku, cluster) series); `tests/sql/test_backtest.py` checks real accuracy (mean MAPE < 50% on the seasonal-naive model against clean synthetic data), not just that rows exist
- [x] Every sku x cluster has a p10 <= p50 <= p90 row per horizon day
- [x] `future_regressors` has a row for every forecast date
- [x] Re-forecast of one series with a play added changes p50 inside the play window and nowhere before it
- [x] Intermittent series (>= 50% zero days) use the labelled average-demand rule — `jobs/sense/forecast.py::SeriesModel` falls back to a flat average with no dow/promo shaping and `forecasts.method = "average_demand_intermittent"`; `tests/sql/test_forecast.py`

## Reviewer-verified
- [x] Model choice per tier matches §5.2 (AI.FORECAST baseline; ARIMA_PLUS_XREG with `on_promo`, `is_festival`, `holiday_region='IN'`) — §5.2 item 2's own three-person-team guidance is to drop the TimesFM baseline and keep only ARIMA_PLUS_XREG (it powers the live beat); the local stand-in does exactly that: one model, always regressor-capable (`on_promo`/`is_festival` multipliers applied unconditionally), plus the separate, distinctly-labelled `average_demand_intermittent` fallback for item 3's sparse-series rule. Two real tiers, not one collapsed into the other
- [x] No `holiday_region` argument on the TimesFM `AI.FORECAST` call
