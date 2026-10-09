---
component: sense_gaps
title: "Sense: gaps"
owner: D
spec_sections: ["2.3", "3.4", "5.2"]
tests: ["tests/sql/test_gaps.py", "tests/sql/test_demand_signals.py", "tests/unit/test_sellby.py"]
---
# Sense: gaps

## Deterministic (CI gate)
- [x] Gap rupees recomputed by an independent SQL implementation equal the pipeline's within 1 rupee
- [x] `online_sellby_breach` uses the versioned `sellby_rule` from the tenant config
- [x] A batch past its online sell-by never yields an online play (only outlet or write-off)
- [x] All six gap types produced with `deadline_type` set correctly
- [x] Gaps validate against `docs/schemas/gap.schema.json`
- [x] `unmet_demand` fires only when real out_of_stock chat requests reach the distinct-customer
  threshold, the pair is not already covered by another gap type this run, and current on-hand
  is zero; below-threshold or since-restocked requests raise nothing
  (`tests/sql/test_demand_signals.py`)
- [x] `stockout_risk` evidence is enriched with `requests_count`/`distinct_customers` when real
  chat requests corroborate it, without changing `rupees_at_stake`

## Reviewer-verified
- [x] `evidence` struct is complete (on_hand, projected_sellthrough, forecast_run_id, sellby_rule) and citable by the Planner
- [x] `data/bigquery/sense/05_gaps.sql` mirrors `jobs/sense/gaps.py`'s `unmet_demand` logic
  (demand-signal aggregation, coverage check, current-on-hand check) for BigQuery parity
