---
component: approve_assignment
title: Approve and assignment
owner: B
spec_sections: ["5.4", "5.6"]
tests: ["tests/unit/test_assignment.py", "tests/api/test_api.py"]
---
# Approve and assignment (`services/api`)

## Deterministic (CI gate)
- [x] Idempotent: double approve produces one assignment set
- [x] Arm assignment reproducible from seed (`FARM_FINGERPRINT(customer_id || seed) % 100 >= holdout * 100` => treated)
- [x] A holdout customer never appears in `offers/`
- [x] `future_regressors` gains the play on approve
- [x] Single-series re-forecast returns in < 15 s on the demo tenant
- [ ] Response matches `docs/openapi.yaml` (`forecast_before/after`, `projected_writeoff_before/after`, `latency_ms`)

## Reviewer-verified
- [ ] UI state after approve matches §5.6 (chart moves, write-off counts down, holdout badge, run-id chip)
