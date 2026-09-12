-- 06_segments.sql
-- KMEANS k=6 on RFM + category share features (DECISIONS §5.2 step 5, §3.3). Segment names are
-- written by hand from the cluster centroids ("{top category} {regulars|occasionals|lapsed|
-- newcomers}"), not generated -- this script proposes the name mechanically as a starting point
-- for that manual pass; a human confirms/edits `taal.segments.name` before it ships.
--
-- Params: @tenant_id STRING, @as_of DATE, @run_id STRING.

CREATE TEMP TABLE customer_features AS
SELECT
  c.tenant_id,
  c.customer_id,
  DATE_DIFF(@as_of, DATE(MAX(o.ts)), DAY) AS recency_days,
  COUNT(DISTINCT o.order_id) / 3.0 AS frequency_per_month,   -- 90-day window scaled to a month
  SUM(ol.qty * (ol.price - IFNULL(ol.discount, 0))) AS monetary_inr,
  ARRAY_AGG(p.category ORDER BY (ol.qty * ol.price) DESC LIMIT 1)[OFFSET(0)] AS top_category
FROM `taal.customers` c
LEFT JOIN `taal.orders` o
  ON o.tenant_id = c.tenant_id AND o.customer_id = c.customer_id
  AND o.ts >= TIMESTAMP(DATE_SUB(@as_of, INTERVAL 90 DAY))
LEFT JOIN `taal.order_lines` ol
  ON ol.tenant_id = o.tenant_id AND ol.order_id = o.order_id
LEFT JOIN `taal.products` p ON p.tenant_id = ol.tenant_id AND p.sku = ol.sku
WHERE c.tenant_id = @tenant_id
GROUP BY c.tenant_id, c.customer_id;

CREATE OR REPLACE MODEL `taal.customer_segments`
OPTIONS(model_type = 'KMEANS', num_clusters = 6, standardize_features = TRUE) AS
SELECT
  IFNULL(recency_days, 9999) AS recency_days,
  IFNULL(frequency_per_month, 0.0) AS frequency_per_month,
  IFNULL(monetary_inr, 0.0) AS monetary_inr
FROM customer_features;

CREATE TEMP TABLE predicted AS
SELECT
  cf.tenant_id, cf.customer_id, cf.top_category,
  CAST(p.CENTROID_ID AS STRING) AS segment_id
FROM ML.PREDICT(
  MODEL `taal.customer_segments`,
  (SELECT customer_id, IFNULL(recency_days, 9999) AS recency_days,
          IFNULL(frequency_per_month, 0.0) AS frequency_per_month,
          IFNULL(monetary_inr, 0.0) AS monetary_inr
   FROM customer_features)
) p
JOIN customer_features cf ON cf.customer_id = p.customer_id;

UPDATE `taal.customers` c
SET c.segment_id = pr.segment_id
FROM predicted pr
WHERE c.tenant_id = @tenant_id AND c.customer_id = pr.customer_id;

CREATE TEMP TABLE centroid_stats AS
SELECT
  segment_id,
  AVG(cf.recency_days) AS recency_days,
  AVG(cf.frequency_per_month) AS frequency_per_month,
  AVG(cf.monetary_inr) AS monetary_inr,
  ARRAY_AGG(cf.top_category ORDER BY cf.monetary_inr DESC LIMIT 1)[OFFSET(0)] AS top_category
FROM predicted pr
JOIN customer_features cf ON cf.customer_id = pr.customer_id
GROUP BY segment_id;

DELETE FROM `taal.segments` WHERE tenant_id = @tenant_id;

-- Mechanical name proposal per DECISIONS §5.2: "{top category} {regulars|occasionals|lapsed|
-- newcomers}" from recency/frequency thresholds. A human overwrites `name` by hand afterwards.
INSERT INTO `taal.segments` (tenant_id, segment_id, name, k, features)
SELECT
  @tenant_id,
  segment_id,
  CONCAT(
    IFNULL(top_category, 'general'), ' ',
    CASE
      WHEN recency_days > 60 THEN 'lapsed'
      WHEN frequency_per_month < 0.5 THEN 'newcomers'
      WHEN frequency_per_month >= 2 THEN 'regulars'
      ELSE 'occasionals'
    END
  ) AS name,
  6 AS k,
  STRUCT(
    recency_days AS recency_days,
    frequency_per_month AS frequency_per_month,
    monetary_inr AS monetary_inr,
    top_category AS top_category
  ) AS features
FROM centroid_stats;
