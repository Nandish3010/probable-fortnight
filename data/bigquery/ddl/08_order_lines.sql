-- Order lines. play_id links a line to the play whose offer produced it (Measure joins on it).
CREATE TABLE IF NOT EXISTS `taal.order_lines` (
  tenant_id STRING NOT NULL,
  order_id STRING NOT NULL,
  line_no INT64 NOT NULL,
  customer_id STRING NOT NULL,
  node_id STRING,
  sku STRING NOT NULL,
  qty INT64,
  price FLOAT64,             -- unit list price at order time
  discount FLOAT64,          -- rupees off per unit
  play_id STRING,
  ts TIMESTAMP NOT NULL
)
PARTITION BY DATE(ts)
CLUSTER BY sku, play_id;
