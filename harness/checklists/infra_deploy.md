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
- [ ] `infra/smoke_test.sh` passes against the live URL -- **written this session**
  (`infra/smoke_test.sh`: health x2, a real gap, a real `/approve`, a real `/chat` reply, all
  under a disposable `X-Taal-Visitor` sandbox so the base tenant is never touched), and a
  `.github/workflows/smoke.yml` (workflow_dispatch + weekly cron) added to run it from a
  GitHub-hosted runner, since this sandbox's egress proxy allows `*.googleapis.com` but blocks
  `*.a.run.app` directly (confirmed: a direct curl to the deployed URLs gets a 403 from the
  proxy). The script itself passed for real, but **not against the literal deployed URL**: GitHub
  refuses to `workflow_dispatch` a workflow that only exists on a non-default branch (404,
  confirmed), and this task does not merge to `main`. What is verified instead is the same script
  run against a local server wired to the exact same live backend (`amru-509214`,
  `asia-south1`, same tenant data) -- see `eval/raw/smoke_test_local_substitute_2026-09-21.txt`.
  Leaving this unticked until someone either runs `infra/smoke_test.sh` by hand against the real
  `*.a.run.app` URLs, or merges this branch so `smoke.yml` can dispatch for real.

## Reviewer-verified
- [x] Region and pinning match §4.4 (asia-south1 with recorded fallback; `google-adk` exact 2.x; `uv.lock` committed)
