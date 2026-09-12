-- Agent trace events (DECISIONS 10): one row per ADK event, replayable by ts_offset_ms.
CREATE TABLE IF NOT EXISTS `taal.execution_events` (
  tenant_id STRING NOT NULL,
  run_id STRING NOT NULL,
  seq INT64 NOT NULL,
  ts TIMESTAMP,
  ts_offset_ms INT64,
  agent STRING,
  event_type STRING,
  payload JSON
)
PARTITION BY DATE(ts)
CLUSTER BY run_id;
