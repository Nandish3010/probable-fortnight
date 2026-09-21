-- A live, ad-hoc concession the Customer Agent negotiated with a customer directly, for a sku
-- with no approved play targeting them (agents/customer/tools.py::negotiate_offer, DECISIONS
-- §5.5). Distinct from `offers` (which mirrors a planner-drafted, holdout-measured play): this
-- table has no play_id, no holdout arm and is never aggregated into play_outcomes. Never written
-- by an LLM -- negotiate_offer computes mechanic/discount_pct/min_qty itself, deterministically,
-- from the category margin floor, the tenant's separate ad-hoc discount ceiling, the shared
-- frequency cap, and whether the customer has ordered before.
CREATE TABLE IF NOT EXISTS `taal.ad_hoc_offers` (
  tenant_id STRING NOT NULL,
  offer_id STRING NOT NULL,
  customer_id STRING NOT NULL,
  sku STRING NOT NULL,
  mechanic STRING NOT NULL,      -- flat_discount | volume_discount
  discount_pct FLOAT64 NOT NULL,
  min_qty INT64,                 -- set only for volume_discount
  session_id STRING,
  ts TIMESTAMP NOT NULL,
  redeemed_at TIMESTAMP
)
PARTITION BY DATE(ts)
CLUSTER BY customer_id, sku;
