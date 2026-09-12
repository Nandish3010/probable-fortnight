-- backtest.sql
-- Rolling-origin backtest, 8 weekly origins, MAPE and bias by rfm_tier and model, written to
-- `taal.eval_forecast` (DECISIONS §5.2 step 8, §17.3 "Sense: forecasts").
--
-- For each origin date (the 8 Mondays ending at @as_of, 7 days apart), forecasts already written
-- to `taal.forecasts` for that origin (as_of = origin, run_id tagged per origin by the calling
-- job) are compared against the sales that actually happened in the 28 days after the origin.
-- This script assumes those historical forecast runs already exist (the Sense job re-runs
-- 02/03/04 at each of the 8 origins before calling this); it only does the comparison.
--
-- Params: @tenant_id STRING, @as_of DATE, @run_id STRING (the run_id under which the eval rows
-- for this backtest are written; distinct from the forecast run_ids being evaluated).

CREATE TEMP TABLE origins AS
SELECT DATE_SUB(@as_of, INTERVAL 7 * w DAY) AS origin_date
FROM UNNEST(GENERATE_ARRAY(1, 8)) AS w;

CREATE TEMP TABLE actuals AS
SELECT
  s.sku, s.node_id, s.date, SUM(s.units) AS actual_units
FROM `taal.sales_daily` s
WHERE s.tenant_id = @tenant_id
GROUP BY s.sku, s.node_id, s.date;

CREATE TEMP TABLE joined AS
SELECT
  o.origin_date,
  f.model,
  c.rfm_tier,
  f.sku, f.node_id, f.date,
  f.p50,
  a.actual_units
FROM origins o
JOIN `taal.forecasts` f
  ON f.tenant_id = @tenant_id AND f.as_of = o.origin_date AND f.node_id IS NOT NULL
JOIN actuals a
  ON a.sku = f.sku AND a.node_id = f.node_id AND a.date = f.date
-- rfm_tier is a customer attribute, not a node/sku one; the backtest buckets by the dominant
-- rfm_tier of the customers who actually bought this sku at this node in the evaluation window,
-- so "MAPE by tier" reads as "how good was the forecast for the demand this tier drives".
LEFT JOIN (
  SELECT ol.sku, ol.node_id,
         ARRAY_AGG(c.rfm_tier ORDER BY COUNT(*) OVER (PARTITION BY ol.sku, ol.node_id, c.rfm_tier) DESC LIMIT 1)[OFFSET(0)] AS rfm_tier
  FROM `taal.order_lines` ol
  JOIN `taal.customers` c ON c.tenant_id = @tenant_id AND c.customer_id = ol.customer_id
  WHERE ol.tenant_id = @tenant_id
  GROUP BY ol.sku, ol.node_id
) c
  ON c.sku = f.sku AND c.node_id = f.node_id
WHERE f.date <= o.origin_date + 27  -- 28-day horizon from that origin
  AND f.date >= o.origin_date;

DELETE FROM `taal.eval_forecast` WHERE tenant_id = @tenant_id AND run_id = @run_id;

INSERT INTO `taal.eval_forecast` (tenant_id, run_id, origin_date, tier, model, mape, bias, n_series, computed_at)
SELECT
  @tenant_id,
  @run_id,
  origin_date,
  IFNULL(rfm_tier, 'unknown') AS tier,
  model,
  -- MAPE excludes zero-actual days (undefined percentage error); this matches how the local
  -- backtest in jobs/sense treats intermittent series -- see docs/DATA_MODEL.md.
  AVG(SAFE_DIVIDE(ABS(p50 - actual_units), actual_units)) AS mape,
  AVG(SAFE_DIVIDE(p50 - actual_units, actual_units)) AS bias,
  COUNT(DISTINCT CONCAT(sku, '|', node_id)) AS n_series,
  CURRENT_TIMESTAMP() AS computed_at
FROM joined
WHERE actual_units > 0
GROUP BY origin_date, tier, model;
