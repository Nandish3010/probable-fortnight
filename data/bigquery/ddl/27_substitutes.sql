-- Precomputed substitute candidates per sku (DECISIONS §5.2 step 6). Stock filtering happens at
-- chat time against Firestore, not here; this table only holds same-category candidate skus.
CREATE TABLE IF NOT EXISTS `taal.substitutes` (
  tenant_id STRING NOT NULL,
  sku STRING NOT NULL,
  candidates ARRAY<STRING>,
  computed_at TIMESTAMP
)
CLUSTER BY tenant_id, sku;
