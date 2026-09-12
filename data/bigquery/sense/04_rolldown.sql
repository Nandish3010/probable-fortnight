-- 04_rolldown.sql
-- Rolls cluster-level forecasts (node_id IS NULL rows written by 02/03) down to node level by
-- trailing 28-day share of sales per sku within the cluster; nodes with no trailing sales for
-- that sku get an equal share of the cluster's remaining nodes (DECISIONS §5.2 step 3).
--
-- Params: @tenant_id STRING, @as_of DATE, @run_id STRING.

CREATE TEMP TABLE node_recent AS
SELECT
  s.tenant_id,
  s.sku,
  n.cluster_id,
  s.node_id,
  SUM(s.units) AS units_28d
FROM `taal.sales_daily` s
JOIN `taal.nodes` n
  ON n.tenant_id = s.tenant_id AND n.node_id = s.node_id
WHERE s.tenant_id = @tenant_id
  AND s.date BETWEEN DATE_SUB(@as_of, INTERVAL 28 DAY) AND DATE_SUB(@as_of, INTERVAL 1 DAY)
GROUP BY s.tenant_id, s.sku, n.cluster_id, s.node_id;

CREATE TEMP TABLE cluster_nodes AS
SELECT tenant_id, cluster_id, node_id
FROM `taal.nodes`
WHERE tenant_id = @tenant_id;

-- shares per (sku, cluster_id): trailing 28-day units per node / cluster total; nodes with no
-- history for the sku fall back to 1 / (number of nodes in the cluster).
CREATE TEMP TABLE cluster_sku AS
SELECT DISTINCT tenant_id, sku, cluster_id
FROM `taal.forecasts`
WHERE tenant_id = @tenant_id AND run_id = @run_id AND node_id IS NULL;

CREATE TEMP TABLE shares AS
SELECT
  cs.tenant_id,
  cs.sku,
  cs.cluster_id,
  cn.node_id,
  SAFE_DIVIDE(IFNULL(nr.units_28d, 0), tot.total_units) AS share_by_sales,
  1.0 / cnt.n_nodes AS share_equal,
  tot.total_units
FROM cluster_sku cs
JOIN cluster_nodes cn
  ON cn.tenant_id = cs.tenant_id AND cn.cluster_id = cs.cluster_id
LEFT JOIN node_recent nr
  ON nr.tenant_id = cs.tenant_id AND nr.sku = cs.sku AND nr.node_id = cn.node_id
LEFT JOIN (
  SELECT tenant_id, sku, cluster_id, SUM(units_28d) AS total_units
  FROM node_recent
  GROUP BY tenant_id, sku, cluster_id
) tot
  ON tot.tenant_id = cs.tenant_id AND tot.sku = cs.sku AND tot.cluster_id = cs.cluster_id
JOIN (
  SELECT tenant_id, cluster_id, COUNT(*) AS n_nodes
  FROM cluster_nodes
  GROUP BY tenant_id, cluster_id
) cnt
  ON cnt.tenant_id = cs.tenant_id AND cnt.cluster_id = cs.cluster_id;

DELETE FROM `taal.forecasts`
WHERE tenant_id = @tenant_id AND run_id = @run_id AND node_id IS NOT NULL;

INSERT INTO `taal.forecasts`
  (tenant_id, run_id, sku, node_id, cluster_id, date, p10, p50, p90, model, method, includes_plays, as_of)
SELECT
  f.tenant_id,
  f.run_id,
  f.sku,
  sh.node_id,
  f.cluster_id,
  f.date,
  f.p10 * IF(sh.total_units IS NULL OR sh.total_units = 0, sh.share_equal, sh.share_by_sales) AS p10,
  f.p50 * IF(sh.total_units IS NULL OR sh.total_units = 0, sh.share_equal, sh.share_by_sales) AS p50,
  f.p90 * IF(sh.total_units IS NULL OR sh.total_units = 0, sh.share_equal, sh.share_by_sales) AS p90,
  f.model,
  f.method,
  f.includes_plays,
  f.as_of
FROM `taal.forecasts` f
JOIN shares sh
  ON sh.tenant_id = f.tenant_id AND sh.sku = f.sku AND sh.cluster_id = f.cluster_id
WHERE f.tenant_id = @tenant_id AND f.run_id = @run_id AND f.node_id IS NULL;
