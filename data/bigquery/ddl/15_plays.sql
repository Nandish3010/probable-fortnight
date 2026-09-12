-- Plays. play_json mirrors docs/schemas/play.schema.json; the scalar columns are denormalised
-- from it for partition pruning and assertions.
CREATE TABLE IF NOT EXISTS `taal.plays` (
  tenant_id STRING NOT NULL,
  play_id STRING NOT NULL,
  gap_id STRING,
  status STRING,
  objective STRING,
  mechanic STRING,
  channel STRING,
  sku STRING,
  target_node_ids ARRAY<STRING>,
  target_batch_ids ARRAY<STRING>,
  window_start TIMESTAMP,
  window_end TIMESTAMP,
  policy_version STRING,
  created_at TIMESTAMP,
  approved_at TIMESTAMP,
  play_json JSON
)
PARTITION BY DATE(created_at)
CLUSTER BY status, sku;
