-- Aggregated style demand signal, by node, garment, colour family and occasion (DECISIONS §5.9).
-- Written by jobs/sense/trends.py, read by GET /trends. Synthetic on the demo tenant: a count of
-- asks the generator and demo script planted, not a forecast; every surface shows it labelled
-- SYNTHETIC. Not read by the Planner or the forecast in this build (see DECISIONS §5.9 "phase 2").
CREATE TABLE IF NOT EXISTS `taal.style_trends` (
  tenant_id STRING NOT NULL,
  run_id STRING NOT NULL,
  node_id STRING,
  window_days INT64,
  garment_type STRING,
  colour_family STRING,
  occasion STRING,
  asks INT64,
  distinct_customers INT64,
  unfulfilled_asks INT64,
  computed_at TIMESTAMP
)
PARTITION BY DATE(computed_at)
CLUSTER BY node_id, garment_type;
