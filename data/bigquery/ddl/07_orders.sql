-- Order headers.
CREATE TABLE IF NOT EXISTS `taal.orders` (
  tenant_id STRING NOT NULL,
  order_id STRING NOT NULL,
  customer_id STRING NOT NULL,
  node_id STRING,
  channel STRING,
  ts TIMESTAMP NOT NULL,
  total_inr FLOAT64
)
PARTITION BY DATE(ts)
CLUSTER BY customer_id;
