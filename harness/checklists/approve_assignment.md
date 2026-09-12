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
- [x] Response matches `docs/openapi.yaml` — `/approve` now has a typed `response_model` (`ApproveResponseOut` in `services/api/main.py`) instead of an untyped dict, so `docs/openapi.yaml` documents the real field names (`forecast.latency_ms`, `forecast.writeoff_before_inr`/`writeoff_after_inr`, not the spec-prose names) and `tests/contract/test_openapi.py` fails on drift

## Reviewer-verified
- [x] UI state after approve matches §5.6 (chart moves, write-off counts down, holdout badge, run-id chip) — `web/tests/live/judge.spec.ts` asserts the chart renders, the write-off line's after-value is strictly less than its before-value (a genuine countdown, not just an arrow), the holdout badge text, and the `refc_<play_id>_...` run-id chip
