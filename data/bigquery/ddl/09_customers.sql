-- Customers (synthetic in the demo tenant; no real PII).
CREATE TABLE IF NOT EXISTS `taal.customers` (
  tenant_id STRING NOT NULL,
  customer_id STRING NOT NULL,
  display_name STRING,
  home_node_id STRING,
  language STRING,           -- en | kn
  rfm_tier STRING,
  segment_id STRING,
  subscription_skus ARRAY<STRING>,
  created_at DATE
)
CLUSTER BY tenant_id, customer_id;
