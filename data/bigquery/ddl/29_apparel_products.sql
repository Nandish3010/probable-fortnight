-- Apparel catalogue for the stylist specialist (DECISIONS §5.9), separate from `products` so the
-- grocery 300-SKU invariants, sell-by rule and gap pipeline are untouched. Small dimension table.
CREATE TABLE IF NOT EXISTS `taal.apparel_products` (
  tenant_id STRING NOT NULL,
  sku STRING NOT NULL,
  name STRING,
  garment_type STRING,
  role STRING,                 -- top | bottom | dress | layer | footwear | accessory
  colour STRING,                -- free-text colour word as shown to the customer
  colour_family STRING,        -- resolved wheel family (agents/stylist/colour.py); never null
  pattern STRING,
  fabric STRING,
  fit STRING,
  occasions ARRAY<STRING>,
  section STRING,               -- women | men | unisex
  metal STRING,                 -- gold | silver | rose gold | oxidised, for jewellery/watches only
  list_price FLOAT64,
  unit_cost FLOAT64,
  season STRING
)
CLUSTER BY tenant_id, sku;
