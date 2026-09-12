---
component: measure
title: Measure
owner: D
spec_sections: ["5.7", "5.8", "18.3"]
tests: ["tests/unit/test_measure.py", "tests/sql/test_measure_tables.py"]
---
# Measure (`jobs/measure`)

## Deterministic (CI gate)
- [x] Fixture with known outcomes reproduces lift and CI to 3 decimals
- [x] A play below `min_treated_n` is `unmeasured`
- [x] Priors update alpha/beta by exact treated responder / non-responder counts
- [x] Dashboard snapshot never shows an unmeasured lift
- [x] Any lift without a holdout fails the job (§17.5)
- [x] Food-waste line computed as units_target_lot x pack weight x cited emissions factor, labelled an estimate
- [ ] `cost_per_play` and `cost_as_pct_of_rupees_at_stake` computed from the billing export fields

## Reviewer-verified
- [ ] Outcomes screen number equals the Looker number equals the README number
