-- 01_regressors.sql
-- Rebuilds `taal.future_regressors` for the next 28 days from @as_of, for this tenant.
-- Implements DECISIONS §5.2 step 2 input / §4.2 ("future regressors from approved plays +
-- festival calendar") and the future_regressors contract in §3.3.
--
-- Two sources, unioned then collapsed to one row per (date, sku, cluster_id):
--   1. Festival calendar: `taal.festival_calendar` rows whose window (date -/+ window_days)
--      covers a forecast date are expanded to every sku in a matching category, every cluster.
--   2. Approved plays: `taal.plays` with status = 'approved' set on_promo = true for their
--      target sku, on every date in [window_start, window_end], for the cluster(s) of their
--      target nodes (DECISIONS §5.4: "inserts the play into future_regressors").
--
-- Params: @tenant_id STRING, @as_of DATE, @run_id STRING (run_id is not stored on this table;
-- accepted for symmetry with the other Sense scripts and to tag the calling job's log line).

DECLARE horizon_start DATE DEFAULT @as_of;
DECLARE horizon_end DATE DEFAULT DATE_ADD(@as_of, INTERVAL 27 DAY);

DELETE FROM `taal.future_regressors`
WHERE tenant_id = @tenant_id
  AND date BETWEEN horizon_start AND horizon_end;

CREATE TEMP TABLE horizon_dates AS
SELECT day AS date
FROM UNNEST(GENERATE_DATE_ARRAY(horizon_start, horizon_end)) AS day;

-- Festival rows: one per (date, sku, cluster_id) where the sku's category is listed on the
-- festival, and the date falls inside the festival's window.
CREATE TEMP TABLE festival_rows AS
SELECT
  h.date,
  p.sku,
  n.cluster_id,
  FALSE AS on_promo,
  TRUE AS is_festival,
  f.name AS festival_name,
  CAST(NULL AS STRING) AS play_id
FROM `taal.festival_calendar` f
JOIN horizon_dates h
  ON h.date BETWEEN DATE_SUB(f.date, INTERVAL f.window_days DAY)
                 AND DATE_ADD(f.date, INTERVAL f.window_days DAY)
JOIN `taal.products` p
  ON p.tenant_id = f.tenant_id AND p.category IN UNNEST(f.categories)
JOIN `taal.nodes` n
  ON n.tenant_id = f.tenant_id
WHERE f.tenant_id = @tenant_id
GROUP BY h.date, p.sku, n.cluster_id, f.name;

-- Play rows: approved plays' target sku, on_promo = true for every date in the play window,
-- for every cluster reached by the play's target nodes.
CREATE TEMP TABLE play_rows AS
SELECT
  h.date,
  pl.sku,
  n.cluster_id,
  TRUE AS on_promo,
  FALSE AS is_festival,
  CAST(NULL AS STRING) AS festival_name,
  pl.play_id
FROM `taal.plays` pl
JOIN UNNEST(pl.target_node_ids) AS target_node_id
JOIN `taal.nodes` n
  ON n.tenant_id = pl.tenant_id AND n.node_id = target_node_id
JOIN horizon_dates h
  ON h.date BETWEEN DATE(pl.window_start) AND DATE(pl.window_end)
WHERE pl.tenant_id = @tenant_id
  AND pl.status = 'approved';

INSERT INTO `taal.future_regressors`
  (tenant_id, date, sku, cluster_id, on_promo, is_festival, festival_name, play_id)
SELECT
  @tenant_id,
  date,
  sku,
  cluster_id,
  LOGICAL_OR(on_promo) AS on_promo,
  LOGICAL_OR(is_festival) AS is_festival,
  ANY_VALUE(festival_name) AS festival_name,
  ANY_VALUE(play_id) AS play_id
FROM (
  SELECT * FROM festival_rows
  UNION ALL
  SELECT * FROM play_rows
)
GROUP BY date, sku, cluster_id;
