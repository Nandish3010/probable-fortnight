-- Future regressors for ARIMA_PLUS_XREG: built nightly from approved plays + festival calendar.
CREATE TABLE IF NOT EXISTS `taal.future_regressors` (
  tenant_id STRING NOT NULL,
  date DATE NOT NULL,
  sku STRING NOT NULL,
  cluster_id STRING NOT NULL,
  on_promo BOOL,
  is_festival BOOL,
  festival_name STRING,
  play_id STRING
)
PARTITION BY date
CLUSTER BY sku, cluster_id;
