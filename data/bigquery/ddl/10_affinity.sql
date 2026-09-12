-- Customer x SKU affinity from co-purchase (0..1).
CREATE TABLE IF NOT EXISTS `taal.affinity` (
  tenant_id STRING NOT NULL,
  customer_id STRING NOT NULL,
  sku STRING NOT NULL,
  score FLOAT64
)
CLUSTER BY tenant_id, customer_id;
