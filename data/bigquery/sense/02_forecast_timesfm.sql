-- 02_forecast_timesfm.sql
-- Baseline forecast per sku x cluster using AI.FORECAST (TimesFM 2.5), horizon 28.
-- Implements DECISIONS §5.2 step 1 / §4.2.
--
-- Two real, verified constraints (run live against asia-south1, not assumed from docs):
-- 1. AI.FORECAST takes no covariate/regressor argument at all -- confirmed by a real 400
--    ("Named argument holiday_region not found in signature"). It owns the nightly baseline
--    only; festival/promo effects and the approve-time re-forecast stay on
--    03_forecast_arima_xreg.sql's ARIMA_PLUS_XREG model, which does take future_regressors.
-- 2. Calling AI.FORECAST over every (sku, cluster_id) pair with no minimum-history filter fails
--    the INSERT below with "Required field date cannot be null": a series too short to forecast
--    comes back with a null forecast_timestamp. qualifying_series (>=28 days of history, the
--    same minimum jobs/sense/backtest.py and the ARIMA_PLUS_XREG job use) fixes it -- confirmed
--    by running the corrected query for real across all 895 qualifying series: 25,060 rows
--    written (895 series x 28-day horizon), ~25s elapsed, ~70MB billed.
--
-- Params: @tenant_id STRING, @as_of DATE, @run_id STRING.

CREATE TEMP TABLE sales_by_cluster AS
SELECT
  s.tenant_id,
  s.date,
  s.sku,
  n.cluster_id,
  SUM(s.units) AS units
FROM `taal.sales_daily` s
JOIN `taal.nodes` n
  ON n.tenant_id = s.tenant_id AND n.node_id = s.node_id
WHERE s.tenant_id = @tenant_id
  AND s.date <= @as_of
GROUP BY s.tenant_id, s.date, s.sku, n.cluster_id;

CREATE TEMP TABLE qualifying_series AS
SELECT sku, cluster_id
FROM sales_by_cluster
GROUP BY sku, cluster_id
HAVING COUNT(*) >= 28;

CREATE TEMP TABLE timesfm_out AS
SELECT
  forecast_timestamp AS date,
  sku,
  cluster_id,
  forecast_value,
  prediction_interval_lower_bound,
  prediction_interval_upper_bound
FROM AI.FORECAST(
  (SELECT b.date, b.sku, b.cluster_id, b.units
   FROM sales_by_cluster b
   JOIN qualifying_series q ON q.sku = b.sku AND q.cluster_id = b.cluster_id),
  data_col => 'units',
  timestamp_col => 'date',
  id_cols => ['sku', 'cluster_id'],
  horizon => 28,
  confidence_level => 0.8
);

INSERT INTO `taal.forecasts`
  (tenant_id, run_id, sku, node_id, cluster_id, date, p10, p50, p90, model, method, includes_plays, as_of)
SELECT
  @tenant_id,
  @run_id,
  sku,
  CAST(NULL AS STRING) AS node_id,   -- cluster-level row; 04_rolldown.sql produces node rows
  cluster_id,
  DATE(date) AS date,
  prediction_interval_lower_bound AS p10,
  forecast_value AS p50,
  prediction_interval_upper_bound AS p90,
  'timesfm' AS model,
  'ai_forecast_timesfm' AS method,
  FALSE AS includes_plays,
  @as_of AS as_of
FROM timesfm_out;
