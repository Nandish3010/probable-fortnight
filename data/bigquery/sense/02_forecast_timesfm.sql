-- 02_forecast_timesfm.sql
-- Baseline forecast per sku x cluster using AI.FORECAST (TimesFM 2.5), horizon 28.
-- Implements DECISIONS §5.2 step 1 / §4.2. TimesFM has no holiday argument -- do NOT pass one;
-- festival effects are handled only by the ARIMA_PLUS_XREG model in 03_forecast_arima_xreg.sql.
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

-- VERIFY: AI.FORECAST option names (confidence_level vs horizon casing, id_cols spelling) as of
-- the BigQuery ML release used for the demo; confirmed against the public docs at time of
-- writing but Google has renamed AI.FORECAST options across preview stages.
CREATE TEMP TABLE timesfm_out AS
SELECT
  forecast_timestamp AS date,
  sku,
  cluster_id,
  forecast_value,
  prediction_interval_lower_bound,
  prediction_interval_upper_bound
FROM AI.FORECAST(
  TABLE sales_by_cluster,
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
