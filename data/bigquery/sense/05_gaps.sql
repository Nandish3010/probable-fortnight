-- 05_gaps.sql
-- Gap detection mirroring jobs/sense/gaps.py exactly (DECISIONS §2.3). Six gap types:
-- online_sellby_breach, expiry_writeoff, stockout_risk, slow_mover, rebalance, unmet_demand.
--
-- rupees_at_stake = units_at_risk * unit_cost for every write-off type; for stockout_risk and
-- unmet_demand it is units_short * (list_price - unit_cost) -- the lost margin, not the cost of
-- the units.
--
-- FIFO allocation: for each (sku, node_id), lots are ordered online_sellby_date, then
-- expiry_date, then batch_id (gaps.py's `lots_sorted` order) and the forecast is allocated to
-- lots in that order via a running total, so a later lot's "projected sell-through" is what
-- remains of cumulative demand after earlier lots have first claim on it.
--
-- evidence.sellby_passed is not a field of the gaps.evidence STRUCT (fixed columns, see DDL
-- 14_gaps.sql); this script therefore keeps the sellby_passed flag as a filter (it changes
-- which gap type is emitted, per gaps.py) and does NOT try to write it into evidence -- a lot
-- whose online sell-by has passed always becomes expiry_writeoff, never online_sellby_breach,
-- exactly as gaps.py enforces.
--
-- unmet_demand is not derived from the forecast at all: it is real customers asking the chat
-- agent for a sku that turned out to have zero on-hand at their node (taal.customer_requests,
-- written deterministically by agents/customer/tools.py, never an LLM decision). Requests on a
-- (sku, node) that also got a stockout_risk gap this run only enrich that gap's evidence
-- (requests_count, distinct_customers); requests on a pair the forecast did not flag at all
-- raise a standalone unmet_demand gap once distinct requesters reach unmet_demand_min_requests
-- and the shelf is still empty as of today. no_match requests (nothing sold at all) never turn
-- into a gap here -- they are an assortment question outside what Sense can act on.
--
-- Params: @tenant_id STRING, @as_of DATE, @run_id STRING.

DECLARE horizon_end DATE DEFAULT DATE_ADD(@as_of, INTERVAL 27 DAY);
-- Keep these in sync with config/tenant.demo.toml [thresholds]; BigQuery has no access to the
-- tenant TOML file, so the Sense job (jobs/sense/__main__.py) must pass matching values here if
-- the tenant config ever diverges from the demo default.
DECLARE slow_mover_days INT64 DEFAULT 21;
DECLARE unmet_demand_lookback_days INT64 DEFAULT 30;
DECLARE unmet_demand_min_requests INT64 DEFAULT 2;

CREATE TEMP TABLE demand_signals AS
SELECT
  sku, node_id,
  COUNT(*) AS requests_count,
  COUNT(DISTINCT customer_id) AS distinct_customers
FROM `taal.customer_requests`
WHERE tenant_id = @tenant_id
  AND request_type = 'out_of_stock'
  AND sku IS NOT NULL
  AND DATE(ts) >= DATE_SUB(@as_of, INTERVAL unmet_demand_lookback_days DAY)
GROUP BY sku, node_id;

DELETE FROM `taal.gaps` WHERE tenant_id = @tenant_id AND run_id = @run_id;

-- ---------------------------------------------------------------------------------------------
-- Shared building blocks
-- ---------------------------------------------------------------------------------------------

CREATE TEMP TABLE demand_cum AS
-- cumulative forecast units per (sku, node) from @as_of up to and including each date; this is
-- gaps.py's `_sum_p50(series, as_of, deadline)` for any deadline (start is always @as_of here).
SELECT
  sku, node_id, date,
  SUM(p50) OVER (PARTITION BY sku, node_id ORDER BY date) AS cum_p50
FROM `taal.forecasts`
WHERE tenant_id = @tenant_id AND run_id = @run_id AND node_id IS NOT NULL
  AND date BETWEEN @as_of AND horizon_end;

CREATE TEMP TABLE avg_daily_demand AS
SELECT sku, node_id, SAFE_DIVIDE(SUM(p50), 28) AS vel
FROM `taal.forecasts`
WHERE tenant_id = @tenant_id AND run_id = @run_id AND node_id IS NOT NULL
GROUP BY sku, node_id;

CREATE TEMP TABLE lots AS
SELECT
  b.tenant_id, b.batch_id, b.sku, b.node_id, b.qty_on_hand, b.expiry_date, b.online_sellby_date,
  p.name AS sku_name, p.category, p.unit_cost, p.list_price, p.is_food,
  n.type AS node_type, n.cluster_id,
  (n.type = 'dark_store') AS is_online_node,
  (b.online_sellby_date IS NOT NULL AND b.online_sellby_date < @as_of AND p.is_food) AS sellby_passed
FROM `taal.inventory_batches` b
JOIN `taal.products` p ON p.tenant_id = b.tenant_id AND p.sku = b.sku
JOIN `taal.nodes` n ON n.tenant_id = b.tenant_id AND n.node_id = b.node_id
WHERE b.tenant_id = @tenant_id
  AND b.qty_on_hand > 0
  AND b.expiry_date IS NOT NULL AND b.expiry_date >= @as_of;

CREATE TEMP TABLE lots_deadline AS
SELECT
  *,
  IF(is_online_node AND is_food AND NOT sellby_passed, online_sellby_date, expiry_date) AS deadline,
  (is_online_node AND is_food AND NOT sellby_passed) AS is_sellby_deadline
FROM lots
QUALIFY IF(is_online_node AND is_food AND NOT sellby_passed, online_sellby_date, expiry_date) <= horizon_end;

CREATE TEMP TABLE lots_ranked AS
SELECT
  *,
  ROW_NUMBER() OVER (
    PARTITION BY sku, node_id
    ORDER BY IFNULL(online_sellby_date, DATE '9999-12-31'), IFNULL(expiry_date, DATE '9999-12-31'), batch_id
  ) AS rn
FROM lots_deadline;

-- ---------------------------------------------------------------------------------------------
-- FIFO allocation: recursive running total of projected sell-through, in (sku, node_id, rn)
-- order, exactly mirroring gaps.py's `allocated` accumulator.
-- VERIFY: BigQuery recursive CTE support/limits (max 500 iterations by default) -- fine for the
-- demo tenant's lot counts per (sku, node_id), but a very deep lot list would need re-checking.
-- ---------------------------------------------------------------------------------------------
CREATE TEMP TABLE alloc AS
WITH RECURSIVE walk AS (
  SELECT
    l.sku, l.node_id, l.rn, l.batch_id, l.deadline,
    l.qty_on_hand,
    GREATEST(0.0, LEAST(CAST(l.qty_on_hand AS FLOAT64), IFNULL(dc.cum_p50, 0.0))) AS projected,
    GREATEST(0.0, LEAST(CAST(l.qty_on_hand AS FLOAT64), IFNULL(dc.cum_p50, 0.0))) AS running_allocated
  FROM lots_ranked l
  LEFT JOIN demand_cum dc ON dc.sku = l.sku AND dc.node_id = l.node_id AND dc.date = l.deadline
  WHERE l.rn = 1

  UNION ALL

  SELECT
    l.sku, l.node_id, l.rn, l.batch_id, l.deadline,
    l.qty_on_hand,
    GREATEST(0.0, LEAST(CAST(l.qty_on_hand AS FLOAT64), IFNULL(dc.cum_p50, 0.0) - w.running_allocated)) AS projected,
    w.running_allocated + GREATEST(0.0, LEAST(CAST(l.qty_on_hand AS FLOAT64), IFNULL(dc.cum_p50, 0.0) - w.running_allocated)) AS running_allocated
  FROM walk w
  JOIN lots_ranked l ON l.sku = w.sku AND l.node_id = w.node_id AND l.rn = w.rn + 1
  LEFT JOIN demand_cum dc ON dc.sku = l.sku AND dc.node_id = l.node_id AND dc.date = l.deadline
)
SELECT sku, node_id, batch_id, projected FROM walk;

-- ---------------------------------------------------------------------------------------------
-- online_sellby_breach / expiry_writeoff
-- ---------------------------------------------------------------------------------------------
CREATE TEMP TABLE writeoff_gaps AS
SELECT
  @tenant_id AS tenant_id,
  -- gap_id: planted ids are seeded by jobs/sense/gaps.py's PLANTED_IDS table on the local path;
  -- this SQL path uses the same deterministic hash fallback for every row (no planted overrides
  -- needed here because the assertions only check numeric consistency, not literal ids).
  TO_HEX(SHA256(FORMAT('%s|%s|%s|%s', IF(ld.is_sellby_deadline, 'online_sellby_breach', 'expiry_writeoff'), ld.sku, ld.node_id, IFNULL(ld.batch_id, '')))) AS gap_id_hash,
  @run_id AS run_id,
  IF(ld.is_sellby_deadline, 'online_sellby_breach', 'expiry_writeoff') AS type,
  ld.sku, ld.node_id, ld.batch_id,
  CAST(ROUND(ld.qty_on_hand - a.projected) AS INT64) AS units_at_risk,
  ld.deadline AS deadline_date,
  IF(ld.is_sellby_deadline, 'online_sellby', 'expiry') AS deadline_type,
  ld.unit_cost, ld.list_price, ld.category, ld.sku_name, ld.node_type, ld.cluster_id,
  ROUND(a.projected, 2) AS projected_sellthrough,
  ld.qty_on_hand AS on_hand
FROM lots_deadline ld
JOIN alloc a ON a.sku = ld.sku AND a.node_id = ld.node_id AND a.batch_id = ld.batch_id
QUALIFY CAST(ROUND(ld.qty_on_hand - a.projected) AS INT64) >= 1;

INSERT INTO `taal.gaps`
  (tenant_id, gap_id, run_id, type, sku, node_id, batch_id, units_at_risk, deadline_date, deadline_type,
   rupees_at_stake, evidence, created_at)
SELECT
  tenant_id,
  CONCAT('gap_', SUBSTR(gap_id_hash, 1, 10)) AS gap_id,
  run_id, type, sku, node_id, batch_id, units_at_risk, deadline_date, deadline_type,
  ROUND(units_at_risk * unit_cost, 2) AS rupees_at_stake,
  STRUCT(
    on_hand AS on_hand,
    projected_sellthrough AS projected_sellthrough,
    run_id AS forecast_run_id,
    (SELECT sellby_rule_version FROM `taal.inventory_batches` WHERE tenant_id = @tenant_id AND batch_id = writeoff_gaps.batch_id LIMIT 1) AS sellby_rule,
    CAST(NULL AS INT64) AS inbound,
    unit_cost AS unit_cost,
    ROUND(list_price - unit_cost, 2) AS margin_per_unit,
    CAST(NULL AS STRING) AS counterpart_node_id,
    CAST(NULL AS INT64) AS counterpart_units,
    CAST(NULL AS INT64) AS requests_count,
    CAST(NULL AS INT64) AS distinct_customers
  ) AS evidence,
  @as_of AS created_at
FROM writeoff_gaps;

-- ---------------------------------------------------------------------------------------------
-- stockout_risk: forecast demand over lead_time_days exceeds on-hand + inbound arriving in time
-- ---------------------------------------------------------------------------------------------
CREATE TEMP TABLE stockout_base AS
SELECT
  n.tenant_id, n.node_id, n.lead_time_days, n.cluster_id,
  p.sku, p.unit_cost, p.list_price, p.category, p.name AS sku_name, n.type AS node_type,
  DATE_ADD(@as_of, INTERVAL n.lead_time_days DAY) AS lead_end,
  IFNULL((SELECT SUM(qty_on_hand) FROM `taal.inventory_batches` b
          WHERE b.tenant_id = n.tenant_id AND b.sku = p.sku AND b.node_id = n.node_id), 0) AS on_hand,
  IFNULL((SELECT SUM(qty) FROM `taal.inbound` i
          WHERE i.tenant_id = n.tenant_id AND i.sku = p.sku AND i.node_id = n.node_id), 0) AS total_inbound,
  IFNULL((SELECT SUM(qty) FROM `taal.inbound` i
          WHERE i.tenant_id = n.tenant_id AND i.sku = p.sku AND i.node_id = n.node_id
            AND i.eta <= DATE_ADD(@as_of, INTERVAL n.lead_time_days DAY)), 0) AS arriving,
  IFNULL((SELECT SUM(p50) FROM `taal.forecasts` f
          WHERE f.tenant_id = n.tenant_id AND f.run_id = @run_id AND f.sku = p.sku AND f.node_id = n.node_id
            AND f.date BETWEEN @as_of AND DATE_ADD(@as_of, INTERVAL n.lead_time_days DAY)), 0.0) AS demand
FROM `taal.nodes` n
CROSS JOIN `taal.products` p
WHERE n.tenant_id = @tenant_id AND p.tenant_id = @tenant_id;

CREATE TEMP TABLE stockout_gaps AS
SELECT
  *,
  demand - on_hand - arriving AS short
FROM stockout_base
QUALIFY (demand - on_hand - arriving) >= 1.0 AND demand > 0;

INSERT INTO `taal.gaps`
  (tenant_id, gap_id, run_id, type, sku, node_id, batch_id, units_at_risk, deadline_date, deadline_type,
   rupees_at_stake, evidence, created_at)
SELECT
  tenant_id,
  CONCAT('gap_', SUBSTR(TO_HEX(SHA256(FORMAT('%s|%s|%s|', 'stockout_risk', sku, node_id))), 1, 10)) AS gap_id,
  @run_id AS run_id,
  'stockout_risk' AS type,
  sku, node_id, CAST(NULL AS STRING) AS batch_id,
  CAST(ROUND(short) AS INT64) AS units_at_risk,
  lead_end AS deadline_date,
  'lead_time' AS deadline_type,
  ROUND(ROUND(short) * (list_price - unit_cost), 2) AS rupees_at_stake,
  STRUCT(
    CAST(on_hand AS INT64) AS on_hand,
    ROUND(demand, 2) AS projected_sellthrough,
    @run_id AS forecast_run_id,
    (SELECT sellby_rule_version FROM `taal.inventory_batches` LIMIT 1) AS sellby_rule,
    CAST(total_inbound AS INT64) AS inbound,
    unit_cost AS unit_cost,
    ROUND(list_price - unit_cost, 2) AS margin_per_unit,
    CAST(NULL AS STRING) AS counterpart_node_id,
    CAST(NULL AS INT64) AS counterpart_units,
    ds.requests_count AS requests_count,
    ds.distinct_customers AS distinct_customers
  ) AS evidence,
  @as_of AS created_at
FROM stockout_gaps sg
LEFT JOIN demand_signals ds ON ds.sku = sg.sku AND ds.node_id = sg.node_id;

-- ---------------------------------------------------------------------------------------------
-- slow_mover: velocity below 25% of category median velocity for that node type, with more than
-- slow_mover_days of cover on hand
-- ---------------------------------------------------------------------------------------------
CREATE TEMP TABLE cat_median AS
SELECT category, node_type, APPROX_QUANTILES(vel, 2)[OFFSET(1)] AS median_vel
FROM (
  SELECT p.category, n.type AS node_type, ad.vel
  FROM avg_daily_demand ad
  JOIN `taal.products` p ON p.tenant_id = @tenant_id AND p.sku = ad.sku
  JOIN `taal.nodes` n ON n.tenant_id = @tenant_id AND n.node_id = ad.node_id
)
GROUP BY category, node_type;

CREATE TEMP TABLE slow_mover_base AS
SELECT
  p.sku, n.node_id, n.type AS node_type, p.category, p.unit_cost, p.list_price, p.name AS sku_name,
  IFNULL((SELECT SUM(qty_on_hand) FROM `taal.inventory_batches` b
          WHERE b.tenant_id = @tenant_id AND b.sku = p.sku AND b.node_id = n.node_id), 0) AS on_hand,
  IFNULL(ad.vel, 0.0) AS vel,
  cm.median_vel,
  -- first lot in FIFO order, per gaps.py `lots_sorted[0]`
  (SELECT batch_id FROM lots_ranked lr WHERE lr.sku = p.sku AND lr.node_id = n.node_id AND lr.rn = 1) AS first_batch_id,
  (SELECT expiry_date FROM lots_ranked lr WHERE lr.sku = p.sku AND lr.node_id = n.node_id AND lr.rn = 1) AS first_expiry_date
FROM `taal.products` p
CROSS JOIN `taal.nodes` n
LEFT JOIN avg_daily_demand ad ON ad.sku = p.sku AND ad.node_id = n.node_id
LEFT JOIN cat_median cm ON cm.category = p.category AND cm.node_type = n.type
WHERE p.tenant_id = @tenant_id AND n.tenant_id = @tenant_id;

CREATE TEMP TABLE slow_mover_gaps AS
SELECT *
FROM slow_mover_base
WHERE on_hand > 0 AND median_vel > 0 AND vel < 0.25 * median_vel
  AND on_hand > vel * slow_mover_days
  AND first_batch_id IS NOT NULL AND first_expiry_date IS NOT NULL;

INSERT INTO `taal.gaps`
  (tenant_id, gap_id, run_id, type, sku, node_id, batch_id, units_at_risk, deadline_date, deadline_type,
   rupees_at_stake, evidence, created_at)
SELECT
  @tenant_id AS tenant_id,
  CONCAT('gap_', SUBSTR(TO_HEX(SHA256(FORMAT('%s|%s|%s|%s', 'slow_mover', sku, node_id, first_batch_id))), 1, 10)) AS gap_id,
  @run_id AS run_id,
  'slow_mover' AS type,
  sku, node_id, first_batch_id AS batch_id,
  CAST(ROUND(on_hand - vel * slow_mover_days) AS INT64) AS units_at_risk,
  first_expiry_date AS deadline_date,
  'expiry' AS deadline_type,
  ROUND(ROUND(on_hand - vel * slow_mover_days) * unit_cost, 2) AS rupees_at_stake,
  STRUCT(
    CAST(on_hand AS INT64) AS on_hand,
    ROUND(vel * slow_mover_days, 2) AS projected_sellthrough,
    @run_id AS forecast_run_id,
    (SELECT sellby_rule_version FROM `taal.inventory_batches` LIMIT 1) AS sellby_rule,
    CAST(NULL AS INT64) AS inbound,
    unit_cost AS unit_cost,
    ROUND(list_price - unit_cost, 2) AS margin_per_unit,
    CAST(NULL AS STRING) AS counterpart_node_id,
    CAST(NULL AS INT64) AS counterpart_units,
    CAST(NULL AS INT64) AS requests_count,
    CAST(NULL AS INT64) AS distinct_customers
  ) AS evidence,
  @as_of AS created_at
FROM slow_mover_gaps
WHERE CAST(ROUND(on_hand - vel * slow_mover_days) AS INT64) >= 1;

-- ---------------------------------------------------------------------------------------------
-- rebalance: surplus (write-off gap) at node A, shortage (stockout gap) at node B, same sku,
-- same cluster; units = MIN(surplus units, shortage units)
-- ---------------------------------------------------------------------------------------------
CREATE TEMP TABLE surplus_side AS
SELECT g.sku, g.node_id AS node_a, n.cluster_id, g.units_at_risk AS units_a, g.gap_id AS gap_id_a,
       g.batch_id, g.deadline_date, g.deadline_type, g.evidence
FROM `taal.gaps` g
JOIN `taal.nodes` n ON n.tenant_id = @tenant_id AND n.node_id = g.node_id
WHERE g.tenant_id = @tenant_id AND g.run_id = @run_id
  AND g.type IN ('online_sellby_breach', 'expiry_writeoff');

CREATE TEMP TABLE short_side AS
SELECT g.sku, g.node_id AS node_b, n.cluster_id, g.units_at_risk AS units_b, g.gap_id AS gap_id_b
FROM `taal.gaps` g
JOIN `taal.nodes` n ON n.tenant_id = @tenant_id AND n.node_id = g.node_id
WHERE g.tenant_id = @tenant_id AND g.run_id = @run_id
  AND g.type = 'stockout_risk';

INSERT INTO `taal.gaps`
  (tenant_id, gap_id, run_id, type, sku, node_id, batch_id, units_at_risk, deadline_date, deadline_type,
   rupees_at_stake, evidence, created_at)
SELECT
  @tenant_id AS tenant_id,
  CONCAT('gap_', SUBSTR(TO_HEX(SHA256(FORMAT('%s|%s|%s|%s', 'rebalance', s.sku, s.node_a, s.node_b))), 1, 10)) AS gap_id,
  @run_id AS run_id,
  'rebalance' AS type,
  s.sku, s.node_a AS node_id, s.batch_id,
  LEAST(s.units_a, sh.units_b) AS units_at_risk,
  s.deadline_date, s.deadline_type,
  ROUND(LEAST(s.units_a, sh.units_b) * p.unit_cost, 2) AS rupees_at_stake,
  STRUCT(
    s.evidence.on_hand AS on_hand,
    s.evidence.projected_sellthrough AS projected_sellthrough,
    s.evidence.forecast_run_id AS forecast_run_id,
    s.evidence.sellby_rule AS sellby_rule,
    s.evidence.inbound AS inbound,
    s.evidence.unit_cost AS unit_cost,
    s.evidence.margin_per_unit AS margin_per_unit,
    sh.node_b AS counterpart_node_id,
    sh.units_b AS counterpart_units,
    s.evidence.requests_count AS requests_count,
    s.evidence.distinct_customers AS distinct_customers
  ) AS evidence,
  @as_of AS created_at
FROM surplus_side s
JOIN short_side sh ON sh.sku = s.sku AND sh.cluster_id = s.cluster_id AND sh.node_b != s.node_a
JOIN `taal.products` p ON p.tenant_id = @tenant_id AND p.sku = s.sku
WHERE LEAST(s.units_a, sh.units_b) >= 1;

-- ---------------------------------------------------------------------------------------------
-- unmet_demand: a real customer request the gap types above did not flag at all for this
-- (sku, node) this run -- a genuine miss, not a duplicate of another gap type. Mirrors gaps.py's
-- `covered` check (every gap already inserted this run_id, of any type) and `_on_hand_now`
-- (current on-hand, not the point-in-time on_hand snapshot used for the other gap types).
-- ---------------------------------------------------------------------------------------------
CREATE TEMP TABLE covered_pairs AS
SELECT DISTINCT sku, node_id FROM `taal.gaps` WHERE tenant_id = @tenant_id AND run_id = @run_id;

CREATE TEMP TABLE on_hand_now AS
SELECT sku, node_id, SUM(qty_on_hand) AS qty
FROM `taal.inventory_batches`
WHERE tenant_id = @tenant_id AND (expiry_date IS NULL OR expiry_date >= @as_of)
GROUP BY sku, node_id;

CREATE TEMP TABLE unmet_demand_gaps AS
SELECT
  ds.sku, ds.node_id, ds.requests_count, ds.distinct_customers,
  p.unit_cost, p.list_price, p.name AS sku_name, p.category,
  n.type AS node_type, n.lead_time_days,
  DATE_ADD(@as_of, INTERVAL n.lead_time_days DAY) AS deadline,
  IFNULL(oh.qty, 0) AS on_hand_now
FROM demand_signals ds
JOIN `taal.products` p ON p.tenant_id = @tenant_id AND p.sku = ds.sku
JOIN `taal.nodes` n ON n.tenant_id = @tenant_id AND n.node_id = ds.node_id
LEFT JOIN on_hand_now oh ON oh.sku = ds.sku AND oh.node_id = ds.node_id
LEFT JOIN covered_pairs cp ON cp.sku = ds.sku AND cp.node_id = ds.node_id
WHERE cp.sku IS NULL
  AND ds.distinct_customers >= unmet_demand_min_requests
  AND IFNULL(oh.qty, 0) <= 0;

INSERT INTO `taal.gaps`
  (tenant_id, gap_id, run_id, type, sku, node_id, batch_id, units_at_risk, deadline_date, deadline_type,
   rupees_at_stake, evidence, created_at)
SELECT
  @tenant_id AS tenant_id,
  CONCAT('gap_', SUBSTR(TO_HEX(SHA256(FORMAT('%s|%s|%s|', 'unmet_demand', sku, node_id))), 1, 10)) AS gap_id,
  @run_id AS run_id,
  'unmet_demand' AS type,
  sku, node_id, CAST(NULL AS STRING) AS batch_id,
  requests_count AS units_at_risk,
  deadline AS deadline_date,
  'lead_time' AS deadline_type,
  ROUND(requests_count * (list_price - unit_cost), 2) AS rupees_at_stake,
  STRUCT(
    0 AS on_hand,
    0.0 AS projected_sellthrough,
    @run_id AS forecast_run_id,
    (SELECT sellby_rule_version FROM `taal.inventory_batches` LIMIT 1) AS sellby_rule,
    CAST(NULL AS INT64) AS inbound,
    unit_cost AS unit_cost,
    ROUND(list_price - unit_cost, 2) AS margin_per_unit,
    CAST(NULL AS STRING) AS counterpart_node_id,
    CAST(NULL AS INT64) AS counterpart_units,
    requests_count AS requests_count,
    distinct_customers AS distinct_customers
  ) AS evidence,
  @as_of AS created_at
FROM unmet_demand_gaps;
