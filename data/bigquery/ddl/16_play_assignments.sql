-- Holdout assignment per play x customer.
CREATE TABLE IF NOT EXISTS `taal.play_assignments` (
  tenant_id STRING NOT NULL,
  play_id STRING NOT NULL,
  customer_id STRING NOT NULL,
  arm STRING NOT NULL,       -- treated | holdout
  assigned_at TIMESTAMP
)
PARTITION BY DATE(assigned_at)
CLUSTER BY play_id;
