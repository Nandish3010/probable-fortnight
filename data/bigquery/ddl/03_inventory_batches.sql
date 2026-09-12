-- Inventory batches (lots). online_sellby_date is derived under the tenant's versioned
-- sellby_rule (agents/gate/sellby.py). Photo-captured rows carry capture_ref.
CREATE TABLE IF NOT EXISTS `taal.inventory_batches` (
  tenant_id STRING NOT NULL,
  batch_id STRING NOT NULL,
  sku STRING NOT NULL,
  node_id STRING NOT NULL,
  qty_on_hand INT64,
  expiry_date DATE,
  online_sellby_date DATE,
  received_at DATE,
  source STRING,             -- system | photo
  capture_ref STRING,
  sellby_rule_version STRING
)
PARTITION BY expiry_date
CLUSTER BY sku, node_id;
