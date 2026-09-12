-- Gaps (DECISIONS 2.3). evidence mirrors docs/schemas/gap.schema.json.
CREATE TABLE IF NOT EXISTS `taal.gaps` (
  tenant_id STRING NOT NULL,
  gap_id STRING NOT NULL,
  run_id STRING,
  type STRING NOT NULL,      -- online_sellby_breach | expiry_writeoff | stockout_risk | rebalance | slow_mover
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
    counterpart_units INT64
  >,
  created_at DATE
)
PARTITION BY deadline_date
CLUSTER BY sku, node_id;
