-- ML.EXPLAIN_FORECAST decomposition for the ARIMA_PLUS_XREG forecast, kept for the Play card's
-- "why this forecast" drawer (DECISIONS §5.2 step 2).
CREATE TABLE IF NOT EXISTS `taal.forecast_explain` (
  tenant_id STRING NOT NULL,
  run_id STRING NOT NULL,
  sku STRING NOT NULL,
  cluster_id STRING NOT NULL,
  date DATE NOT NULL,
  time_series_type STRING,       -- history | forecast
  trend FLOAT64,
  seasonal_period_yearly FLOAT64,
  seasonal_period_weekly FLOAT64,
  holiday_effect FLOAT64,
  xreg_on_promo FLOAT64,
  xreg_is_festival FLOAT64,
  residual FLOAT64
)
PARTITION BY date
CLUSTER BY sku, cluster_id;
