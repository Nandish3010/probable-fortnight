-- What a customer actually asked for and could not get, across every session (DECISIONS: chat as a
-- demand signal). Sense reads this to enrich stockout_risk evidence and to raise the unmet_demand
-- gap type for situations the forecast alone would have missed. Never written by an LLM: get_stock
-- and list_products record a row themselves, deterministically, whenever they turn up nothing.
CREATE TABLE IF NOT EXISTS `taal.customer_requests` (
  tenant_id STRING NOT NULL,
  customer_id STRING NOT NULL,
  node_id STRING NOT NULL,
  sku STRING,                -- set for out_of_stock (a real product with zero on-hand); null for no_match
  query_text STRING,         -- the words that produced a no_match; null for out_of_stock
  request_type STRING NOT NULL,  -- out_of_stock | no_match
  session_id STRING,
  ts TIMESTAMP NOT NULL
)
PARTITION BY DATE(ts)
CLUSTER BY sku, node_id;
