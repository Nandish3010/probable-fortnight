-- Inbound purchase orders not yet received.
CREATE TABLE IF NOT EXISTS `taal.inbound` (
  tenant_id STRING NOT NULL,
  po_id STRING NOT NULL,
  sku STRING NOT NULL,
  node_id STRING NOT NULL,
  qty INT64,
  eta DATE
)
PARTITION BY eta
CLUSTER BY sku, node_id;
