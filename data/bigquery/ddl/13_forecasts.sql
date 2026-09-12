-- Forecasts per sku x node (rolled down from sku x cluster). model: timesfm | arima_xreg.
-- method labels the concrete rule used (e.g. intermittent series use average demand).
CREATE TABLE IF NOT EXISTS `taal.forecasts` (
  tenant_id STRING NOT NULL,
  run_id STRING NOT NULL,
  sku STRING NOT NULL,
  node_id STRING,
  cluster_id STRING,
  date DATE NOT NULL,
  p10 FLOAT64,
  p50 FLOAT64,
  p90 FLOAT64,
  model STRING,
  method STRING,
  includes_plays BOOL,
  as_of DATE
)
PARTITION BY date
CLUSTER BY sku, node_id;
