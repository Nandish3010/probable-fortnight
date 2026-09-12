-- Measured outcomes per play x arm (DECISIONS 5.7). waste_kg_est / co2e_kg_est are labelled estimates.
CREATE TABLE IF NOT EXISTS `taal.play_outcomes` (
  tenant_id STRING NOT NULL,
  play_id STRING NOT NULL,
  arm STRING NOT NULL,
  customers INT64,
  responders INT64,
  units_target_lot INT64,
  revenue FLOAT64,
  margin FLOAT64,
  discount_cost FLOAT64,
  waste_avoided FLOAT64,
  lift FLOAT64,
  ci_low FLOAT64,
  ci_high FLOAT64,
  status STRING,             -- measured | unmeasured
  min_treated_n INT64,
  waste_kg_est FLOAT64,
  co2e_kg_est FLOAT64,
  emissions_factor_kgco2e_per_kg FLOAT64,
  net_margin_per_discount_inr FLOAT64,
  computed_at TIMESTAMP
)
PARTITION BY DATE(computed_at)
CLUSTER BY play_id;
