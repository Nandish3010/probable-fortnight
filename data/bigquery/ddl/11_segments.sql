-- Segments: KMEANS k = 6 on RFM + category share; names written by hand.
CREATE TABLE IF NOT EXISTS `taal.segments` (
  tenant_id STRING NOT NULL,
  segment_id STRING NOT NULL,
  name STRING,
  k INT64,
  features STRUCT<recency_days FLOAT64, frequency_per_month FLOAT64, monetary_inr FLOAT64, top_category STRING>
)
CLUSTER BY tenant_id, segment_id;
