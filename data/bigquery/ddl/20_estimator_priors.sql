-- Beta priors for response rate per (mechanic, category, segment). Weak by construction.
CREATE TABLE IF NOT EXISTS `taal.estimator_priors` (
  tenant_id STRING NOT NULL,
  mechanic STRING NOT NULL,
  category STRING NOT NULL,
  segment_id STRING NOT NULL,
  alpha FLOAT64,
  beta FLOAT64,
  n_measured INT64,
  updated_at TIMESTAMP
)
CLUSTER BY tenant_id, mechanic, category;
