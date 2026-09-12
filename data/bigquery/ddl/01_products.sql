-- Products: one row per SKU. Small table; clustered so lookups by sku prune.
CREATE TABLE IF NOT EXISTS `taal.products` (
  tenant_id STRING NOT NULL,
  sku STRING NOT NULL,
  name STRING,
  category STRING,
  pack_size STRING,
  pack_weight_g INT64,
  unit_cost FLOAT64,
  list_price FLOAT64,
  margin_floor_pct FLOAT64,
  shelf_life_days INT64,
  is_food BOOL
)
CLUSTER BY tenant_id, sku;
