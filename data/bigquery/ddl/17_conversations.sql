CREATE TABLE IF NOT EXISTS `taal.conversations` (
  tenant_id STRING NOT NULL,
  session_id STRING NOT NULL,
  customer_id STRING,
  channel STRING,
  play_id STRING,
  started_at TIMESTAMP
)
PARTITION BY DATE(started_at)
CLUSTER BY customer_id;
