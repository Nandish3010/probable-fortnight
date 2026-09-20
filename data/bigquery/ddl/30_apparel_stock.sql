-- Per-(sku, node, size) stock snapshot for apparel. Dark stores only (no outlet apparel in v1).
CREATE TABLE IF NOT EXISTS `taal.apparel_stock` (
  tenant_id STRING NOT NULL,
  sku STRING NOT NULL,
  node_id STRING NOT NULL,
  size STRING NOT NULL,
  qty_on_hand INT64,
  as_of DATE
)
PARTITION BY as_of
CLUSTER BY sku, node_id;
