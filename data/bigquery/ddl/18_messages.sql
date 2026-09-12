CREATE TABLE IF NOT EXISTS `taal.messages` (
  tenant_id STRING NOT NULL,
  session_id STRING NOT NULL,
  message_id STRING NOT NULL,
  customer_id STRING,
  channel STRING,
  role STRING,               -- user | agent | tool
  text STRING,
  tool_calls JSON,
  citations JSON,
  latency_ms INT64,
  ts TIMESTAMP
)
PARTITION BY DATE(ts)
CLUSTER BY session_id;
