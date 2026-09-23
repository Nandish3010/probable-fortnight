-- 03_forecast_arima_xreg.sql
-- ARIMA_PLUS_XREG per sku x cluster, trained nightly, with future_regressors as the covariate
-- table (holiday_region 'IN', regressors on_promo + is_festival). Implements DECISIONS §5.2
-- step 2 and §4.2 ("forecast re-run for the affected series with the play as a covariate").
--
-- Model names cannot take a query parameter, so this script loops over the sku x cluster pairs
-- that have enough history and issues one CREATE OR REPLACE MODEL + ML.FORECAST per pair via
-- EXECUTE IMMEDIATE. Pattern: `taal.arima_xreg_{sku_cluster}`, sanitised to a legal identifier.
--
-- Params: @tenant_id STRING, @as_of DATE, @run_id STRING.

CREATE TEMP TABLE train_series AS
SELECT
  s.tenant_id,
  s.date,
  s.sku,
  n.cluster_id,
  SUM(s.units) AS units,
  LOGICAL_OR(s.on_promo) AS on_promo
FROM `taal.sales_daily` s
JOIN `taal.nodes` n
  ON n.tenant_id = s.tenant_id AND n.node_id = s.node_id
WHERE s.tenant_id = @tenant_id
  AND s.date <= @as_of
GROUP BY s.tenant_id, s.date, s.sku, n.cluster_id;

-- Join in is_festival so training data carries the same xreg columns as future_regressors.
CREATE TEMP TABLE train_series_xreg AS
SELECT
  t.*,
  COALESCE(f.is_festival, FALSE) AS is_festival
FROM train_series t
LEFT JOIN `taal.future_regressors` f
  ON f.tenant_id = t.tenant_id AND f.sku = t.sku AND f.cluster_id = t.cluster_id AND f.date = t.date;

CREATE TEMP TABLE series_pairs AS
SELECT sku, cluster_id, COUNT(*) AS n_days
FROM train_series_xreg
GROUP BY sku, cluster_id
HAVING n_days >= 28;   -- ARIMA_PLUS_XREG needs enough history; thinner series stay on TimesFM only

BEGIN
  DECLARE i INT64 DEFAULT 0;
  DECLARE n INT64;
  DECLARE cur_sku STRING;
  DECLARE cur_cluster STRING;
  DECLARE model_suffix STRING;
  DECLARE model_name STRING;
  DECLARE sql_text STRING;

  SET n = (SELECT COUNT(*) FROM series_pairs);

  WHILE i < n DO
    -- BigQuery scripting's LIMIT/OFFSET rejects a variable in the OFFSET position ("OFFSET
    -- expects an integer literal or parameter"); ROW_NUMBER() indexed by the loop variable is
    -- the workaround. Found and fixed by actually running this script -- see eval/raw/ for the
    -- real BigQuery job this was verified against.
    SET (cur_sku, cur_cluster) = (
      SELECT AS STRUCT sku, cluster_id
      FROM (
        SELECT sku, cluster_id, ROW_NUMBER() OVER (ORDER BY sku, cluster_id) - 1 AS rn
        FROM series_pairs
      )
      WHERE rn = i
    );
    -- sanitise sku/cluster into a legal BigQuery model id fragment
    SET model_suffix = REGEXP_REPLACE(LOWER(cur_sku || '_' || cur_cluster), r'[^a-z0-9_]', '_');
    SET model_name = 'taal.arima_xreg_' || model_suffix;

    SET sql_text = FORMAT("""
      CREATE OR REPLACE MODEL `%s`
      OPTIONS(
        MODEL_TYPE = 'ARIMA_PLUS_XREG',
        TIME_SERIES_TIMESTAMP_COL = 'date',
        TIME_SERIES_DATA_COL = 'units',
        TIME_SERIES_ID_COL = ['sku', 'cluster_id'],
        HOLIDAY_REGION = 'IN'
      ) AS
      SELECT date, sku, cluster_id, units, on_promo, is_festival
      FROM `taal.arima_train_%s`
    """, model_name, model_suffix);

    -- materialise this series' training slice under a name EXECUTE IMMEDIATE can reference
    EXECUTE IMMEDIATE FORMAT(
      "CREATE OR REPLACE TABLE `taal.arima_train_%s` AS SELECT date, sku, cluster_id, units, on_promo, is_festival FROM train_series_xreg WHERE sku = @s AND cluster_id = @c",
      model_suffix
    ) USING cur_sku AS s, cur_cluster AS c;

    EXECUTE IMMEDIATE sql_text;

    -- forecast this series with the (already rebuilt, see 01_regressors.sql) future_regressors
    EXECUTE IMMEDIATE FORMAT("""
      INSERT INTO `taal.forecasts`
        (tenant_id, run_id, sku, node_id, cluster_id, date, p10, p50, p90, model, method, includes_plays, as_of)
      SELECT
        @tenant_id, @run_id, sku, CAST(NULL AS STRING), cluster_id, DATE(forecast_timestamp),
        prediction_interval_lower_bound, forecast_value, prediction_interval_upper_bound,
        'arima_xreg', 'arima_plus_xreg', TRUE, @as_of
      FROM ML.FORECAST(
        MODEL `%s`,
        STRUCT(28 AS horizon, 0.8 AS confidence_level),
        (SELECT date, sku, cluster_id, on_promo, is_festival FROM `taal.future_regressors`
               WHERE tenant_id = @tenant_id AND sku = @s AND cluster_id = @c)
      )
    """, model_name)
    USING @tenant_id AS tenant_id, @run_id AS run_id, @as_of AS as_of, cur_sku AS s, cur_cluster AS c;

    -- decomposition for the Play card's "why this forecast" drawer. Column names and the
    -- required third (data table) argument verified by actually running this against real
    -- BigQuery, not from docs: ARIMA_PLUS_XREG's ML.EXPLAIN_FORECAST needs the same data table
    -- ML.FORECAST does, and names its per-regressor columns attribution_<name>, not
    -- xreg_<name>_coefficient as originally guessed here.
    EXECUTE IMMEDIATE FORMAT("""
      INSERT INTO `taal.forecast_explain`
        (tenant_id, run_id, sku, cluster_id, date, time_series_type, trend,
         seasonal_period_yearly, seasonal_period_weekly, holiday_effect,
         xreg_on_promo, xreg_is_festival, residual)
      SELECT
        @tenant_id, @run_id, sku, cluster_id, DATE(time_series_timestamp), time_series_type,
        trend, seasonal_period_yearly, seasonal_period_weekly, holiday_effect,
        IFNULL(attribution_on_promo, 0.0), IFNULL(attribution_is_festival, 0.0), residual
      FROM ML.EXPLAIN_FORECAST(
        MODEL `%s`,
        STRUCT(28 AS horizon, 0.8 AS confidence_level),
        (SELECT date, sku, cluster_id, on_promo, is_festival FROM `taal.future_regressors`
               WHERE tenant_id = @tenant_id AND sku = @s AND cluster_id = @c)
      )
    """, model_name)
    USING @tenant_id AS tenant_id, @run_id AS run_id, cur_sku AS s, cur_cluster AS c;

    SET i = i + 1;
  END WHILE;
END;
