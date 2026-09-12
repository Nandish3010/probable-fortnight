---
component: infra_deploy
title: Infra and deploy
owner: D
spec_sections: ["4.1", "4.4", "4.5", "18.3"]
tests: ["make secrets", "tests/api/test_api.py"]
---
# Infra and deploy (`infra/`)

## Deterministic (CI gate)
- [ ] `make deploy` from a clean project succeeds (three Cloud Run services, one job, one Scheduler)
- [x] `/health` reports all four dependencies (BigQuery, Firestore, Vertex, Sessions) with timestamps
- [ ] IAM matrix applied: each service account least-privilege, checked by `infra/iam_check.sh`
- [x] Secrets absent from the repo (`make secrets`)
- [x] Model IDs only in `config/models.toml`
- [ ] Budget alerts exist at $50 / $100 / $200 (`infra/budgets.sh`)
- [ ] `infra/smoke_test.sh` passes against the live URL

## Reviewer-verified
- [x] Region and pinning match §4.4 (asia-south1 with recorded fallback; `google-adk` exact 2.x; `uv.lock` committed)
