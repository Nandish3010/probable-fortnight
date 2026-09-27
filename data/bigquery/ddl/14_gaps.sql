-- Gaps (DECISIONS 2.3). evidence mirrors docs/schemas/gap.schema.json.
CREATE TABLE IF NOT EXISTS `taal.gaps` (
  tenant_id STRING NOT NULL,
  gap_id STRING NOT NULL,
  run_id STRING,
  type STRING NOT NULL,      -- online_sellby_breach | expiry_writeoff | stockout_risk | rebalance | slow_mover | unmet_demand
  sku STRING NOT NULL,
  node_id STRING NOT NULL,
  batch_id STRING,
  units_at_risk INT64,
  deadline_date DATE,
  deadline_type STRING,      -- online_sellby | expiry | lead_time
  rupees_at_stake FLOAT64,
  evidence STRUCT<
    on_hand INT64,
    projected_sellthrough FLOAT64,
    forecast_run_id STRING,
    sellby_rule STRING,
    inbound INT64,
    unit_cost FLOAT64,
    margin_per_unit FLOAT64,
    counterpart_node_id STRING,
    counterpart_units INT64,
    counterpart_gap_id STRING,  -- rebalance gaps only (jobs/sense/gaps.py); missing here until 2026-09-27,
                                -- found live the first time a rebalance gap was ever written to real BigQuery
    requests_count INT64,      -- real out_of_stock chat requests corroborating this gap (stockout_risk, unmet_demand)
    distinct_customers INT64,
    -- The fields below are real evidence keys jobs/sense/gaps.py has always emitted for other gap
    -- types (online_sellby_breach/expiry_writeoff, stockout_risk, slow_mover, unmet_demand,
    -- assortment_gap) that this STRUCT never declared -- found live 2026-09-27, the first time a
    -- write of each of those gap types was ever attempted against real BigQuery. All additive,
    -- nullable fields; no existing field changed.
    expiry_date STRING,             -- online_sellby_breach / expiry_writeoff
    online_sellby_date STRING,      -- online_sellby_breach / expiry_writeoff
    sellby_passed BOOL,             -- online_sellby_breach / expiry_writeoff
    sku_name STRING,                -- most gap types
    category STRING,                -- most gap types
    node_type STRING,               -- most gap types
    lead_time_days INT64,           -- stockout_risk
    velocity_per_day FLOAT64,       -- slow_mover
    category_median_velocity FLOAT64, -- slow_mover
    slow_mover_days INT64,          -- slow_mover
    requesting_customer_ids ARRAY<STRING>, -- assortment_gap
    supply_node_id STRING,          -- assortment_gap
    garment_type STRING,            -- assortment_gap
    colour_family STRING            -- assortment_gap
  >,
  created_at DATE
)
PARTITION BY deadline_date
CLUSTER BY sku, node_id;
