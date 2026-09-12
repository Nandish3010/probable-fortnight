CREATE TABLE IF NOT EXISTS `taal.eval_forecast` (
  tenant_id STRING NOT NULL,
  run_id STRING NOT NULL,
  origin_date DATE,
  tier STRING,
  model STRING,
  mape FLOAT64,
  bias FLOAT64,
  n_series INT64,
  computed_at TIMESTAMP
)
PARTITION BY origin_date
CLUSTER BY tier, model;
