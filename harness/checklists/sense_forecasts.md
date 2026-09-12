---
component: sense_forecasts
title: "Sense: forecasts"
owner: D
spec_sections: ["5.2", "4.2"]
tests: ["tests/sql/test_forecast.py"]
---
# Sense: forecasts (`jobs/sense`, `data/bigquery`)

## Deterministic (CI gate)
- [ ] Backtest job runs on the sample slice (rolling origin, 8 weeks)
- [ ] MAPE and bias per tier and model computed and written to `eval_forecast`
- [x] Every sku x cluster has a p10 <= p50 <= p90 row per horizon day
- [x] `future_regressors` has a row for every forecast date
- [x] Re-forecast of one series with a play added changes p50 inside the play window and nowhere before it
- [ ] Intermittent series (>= 50% zero days) use the labelled average-demand rule

## Reviewer-verified
- [ ] Model choice per tier matches §5.2 (AI.FORECAST baseline; ARIMA_PLUS_XREG with `on_promo`, `is_festival`, `holiday_region='IN'`)
- [x] No `holiday_region` argument on the TimesFM `AI.FORECAST` call
