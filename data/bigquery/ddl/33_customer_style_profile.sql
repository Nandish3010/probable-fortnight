-- A customer's own coarse skin-tone profile for the stylist (DECISIONS §5.9). One live row per
-- customer (upserted by customer_id). The selfie image itself is NEVER stored anywhere -- only the
-- two coarse enums below, and only once the customer has confirmed the read. Gated by a
-- `consent(purpose="style_profile")` row; `withdrawn_at` here mirrors that consent being withdrawn
-- ("forget my skin tone" deletes both). Never joined by Sense, style_trends or the Planner.
CREATE TABLE IF NOT EXISTS `taal.customer_style_profile` (
  tenant_id STRING NOT NULL,
  customer_id STRING NOT NULL,
  undertone STRING,             -- warm | cool | neutral
  depth STRING,                 -- light | medium | deep
  source STRING,                -- declared | selfie
  confidence FLOAT64,            -- null when source = declared
  confirmed BOOL,
  ts TIMESTAMP NOT NULL,
  withdrawn_at TIMESTAMP
)
PARTITION BY DATE(ts)
CLUSTER BY customer_id;
