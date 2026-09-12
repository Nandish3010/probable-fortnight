-- Daily sales per sku x node. Partitioned by date, clustered by sku (DECISIONS 3.3).
CREATE TABLE IF NOT EXISTS `taal.sales_daily` (
  tenant_id STRING NOT NULL,
  date DATE NOT NULL,
  sku STRING NOT NULL,
  node_id STRING NOT NULL,
  units INT64,
  revenue FLOAT64,
  on_promo BOOL
)
PARTITION BY date
CLUSTER BY sku;
