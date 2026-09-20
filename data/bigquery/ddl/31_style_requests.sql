-- What a customer asked the stylist for and whether it was fulfilled, across every session
-- (DECISIONS §5.9, mirrors `customer_requests` for the grocery agent). Never written by an LLM:
-- find_apparel and suggest_pairings record a row themselves, deterministically, on every ask.
-- Never carries a skin-tone field -- the style profile (customer_style_profile) is a separate,
-- consent-gated table and is never aggregated here or in style_trends.
CREATE TABLE IF NOT EXISTS `taal.style_requests` (
  tenant_id STRING NOT NULL,
  customer_id STRING NOT NULL,
  node_id STRING NOT NULL,
  session_id STRING,
  ts TIMESTAMP NOT NULL,
  source STRING NOT NULL,       -- find_apparel | suggest_pairings
  garment_type STRING,
  colour STRING,
  colour_family STRING,
  occasion STRING,
  query_text STRING,
  matched_sku STRING,
  fulfilled BOOL
)
PARTITION BY DATE(ts)
CLUSTER BY node_id, garment_type;
