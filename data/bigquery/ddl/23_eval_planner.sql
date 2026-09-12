CREATE TABLE IF NOT EXISTS `taal.eval_planner` (
  tenant_id STRING NOT NULL,
  run_id STRING NOT NULL,
  gap_id STRING,
  schema_valid BOOL,
  gate_pass BOOL,
  iterations INT64,
  trajectory_match BOOL,
  mechanic STRING,
  computed_at TIMESTAMP
)
PARTITION BY DATE(computed_at)
CLUSTER BY run_id;
