---
component: sense_gaps
title: "Sense: gaps"
owner: D
spec_sections: ["2.3", "3.4", "5.2"]
tests: ["tests/sql/test_gaps.py", "tests/unit/test_sellby.py"]
---
# Sense: gaps

## Deterministic (CI gate)
- [x] Gap rupees recomputed by an independent SQL implementation equal the pipeline's within 1 rupee
- [x] `online_sellby_breach` uses the versioned `sellby_rule` from the tenant config
- [x] A batch past its online sell-by never yields an online play (only outlet or write-off)
- [x] All five gap types produced with `deadline_type` set correctly
- [x] Gaps validate against `docs/schemas/gap.schema.json`

## Reviewer-verified
- [x] `evidence` struct is complete (on_hand, projected_sellthrough, forecast_run_id, sellby_rule) and citable by the Planner
