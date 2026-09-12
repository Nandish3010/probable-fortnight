CREATE TABLE IF NOT EXISTS `taal.eval_copy` (
  tenant_id STRING NOT NULL,
  run_id STRING NOT NULL,
  play_id STRING,
  variant_idx INT64,
  language STRING,
  validator_pass BOOL,
  disclosure_included BOOL,
  regenerated BOOL,
  computed_at TIMESTAMP
)
PARTITION BY DATE(computed_at)
CLUSTER BY run_id;
