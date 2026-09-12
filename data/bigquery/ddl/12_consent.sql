-- Consent per customer x channel x purpose (DECISIONS 2.6). withdrawn_at set on STOP.
CREATE TABLE IF NOT EXISTS `taal.consent` (
  tenant_id STRING NOT NULL,
  customer_id STRING NOT NULL,
  channel STRING NOT NULL,
  purpose STRING NOT NULL,
  source STRING,
  ts TIMESTAMP NOT NULL,
  withdrawn_at TIMESTAMP
)
PARTITION BY DATE(ts)
CLUSTER BY customer_id;
