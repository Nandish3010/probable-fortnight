-- Nodes: dark stores and physical outlets with coordinates and lead time.
CREATE TABLE IF NOT EXISTS `taal.nodes` (
  tenant_id STRING NOT NULL,
  node_id STRING NOT NULL,
  name STRING,
  type STRING,               -- dark_store | outlet
  lat FLOAT64,
  lng FLOAT64,
  lead_time_days INT64,
  cluster_id STRING
)
CLUSTER BY tenant_id, node_id;
