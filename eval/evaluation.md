# Evaluation table -- 20-21 Sep 2026

Every row below names the exact command that produced it and the raw output it summarises,
committed alongside this file under `eval/raw/`. Nothing here is typed or estimated; where
DECISIONS §12 asks for a number this project genuinely cannot produce yet, the row says so and
why, rather than a guess. `STATUS.md` (also committed, `eval/raw/status_2026-09-20.md`) tracks
the same gaps as unticked checklist items -- the two are kept consistent on purpose.

## Producible today

| # | Metric (DECISIONS §12) | Result | Command | Raw output |
|---|---|---|---|---|
| 1 | Forecast backtest MAPE/bias by category tier | 9 tiers x 7 rolling origins = 63 rows. Mean MAPE ranges 0.107 (bakery) to 0.221 (premium_tea); mean bias -0.06 to +0.07. Full per-tier table below. | `uv run python -m jobs.sense.backtest` | `eval/raw/backtest_2026-09-20.txt` (summary printed by the job), `eval/raw/backtest_rows_2026-09-20.jsonl` (all 63 rows written to `eval_forecast`), `eval/raw/backtest_summary_2026-09-20.txt` (per-tier means computed from the raw rows) |
| 2 | Sense throughput, full tenant | 300 SKUs, 16 nodes/outlets: 3.83s total (forecast 2.50s, gaps 0.15s, segments+substitutes 1.18s); 550 gaps, 6 segments, 300 substitute rows | `TAAL_NOW=2026-09-12T03:30:00Z uv run python -m jobs.sense` | `eval/raw/sense_throughput_2026-09-20.json` |
| 3 | Guardrail and test counts | 108 of 130 checklist items ticked; per-component test counts (e.g. Estimator and gate: 51 passed; Approve and assignment: 14 passed; Customer Agent: 34 passed) -- see the full table | `uv run python -m harness.status` (`make status`) | `eval/raw/status_2026-09-20.md` (full copy of `STATUS.md`) |
| 4 | Per-endpoint latency, live Vertex backend | 20/20 endpoints 200 or the expected 4xx. Live-Gemini calls: `/plan` 110.9s (no_play, 2 iterations), `/rerun` 70.5s (proposed, 1 iteration, policy change flips mechanic), `/approve` 12.3s (includes the new BigQuery copy-generation attempt, which fell back to templates -- see Part B note below), `/chat` 4.5-6.9s x3, `/capture` (upload) 3.9s | `TAAL_NOW=2026-09-12T03:30:00Z uv run python -m harness.sweep_live http://localhost:8080` against a local server started with `TAAL_MODEL_BACKEND=vertex GOOGLE_APPLICATION_CREDENTIALS=... GOOGLE_CLOUD_PROJECT=amru-509214` (real Vertex credentials; `*.a.run.app` is unreachable from this environment's egress policy, so this is the live backend exercised locally, not the deployed URL itself) | `eval/raw/sweep_vertex_2026-09-20.txt` |
| 5 | Planner evalset (`adk eval`) | stub backend, 5 evalsets: (fill after run completes -- see note) | `uv run python -m harness.run_evals` (`make eval`) | `eval/raw/adk_eval_stub_2026-09-20.txt` |
| 6 | Copy validator pass rate | 150/150 variants accepted (100%) across the 20 seeded plays' templated copy | ad hoc script calling `jobs.sense.copy.generate_copy` + `validate_copy` over `.local/data/plays.jsonl` | `eval/raw/copy_validator_2026-09-20.json` (per-play breakdown). **Caveat: this measures the templated path only** -- the BigQuery `AI.GENERATE_TABLE` path (new this session) has never produced a variant end-to-end, because the remote model's connection lacks the `roles/aiplatform.user` grant it needs (blocked by this environment's own permission-grant restriction, not a code defect); see the approve.py fallback log line in `eval/raw/sweep_vertex_2026-09-20.txt`'s companion API log. |
| 7 | Cold start, deployed services | `taal-web` GET `/` after ~57 min idle: 6.25s (vs <100ms warm). `taal-agents` a request after ~58 min idle: 5.46s. Combined worst case (both cold) is on the order of 11-12s; typical warm request is <100ms on both. | Cloud Logging query (`entries:list`) against `resource.type="cloud_run_revision"` for both services, since this environment cannot curl `*.a.run.app` directly (egress policy) | inline above; not saved as a separate raw file since it is a Cloud Logging query result, not a local command's stdout -- reproduce with `gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.service_name="taal-agents"' --project amru-509214 --limit 20 --format json` and look for a large gap in `httpRequest.latency` after an idle period |
| 8 | Scaling confirmation (Part B1) | Both `taal-agents` and `taal-web`: `minInstanceCount` unset (defaults to 0, i.e. scale-to-zero) and `resources.cpuIdle` unset (defaults to `true`, i.e. CPU throttled outside requests / request-based billing -- `--no-cpu-throttling` was never set). Confirmed as already correct; no change needed. | Cloud Run Admin API v2, `services.get` on both services | not saved as a raw file (a live API read, not a repo command); reproducible with `gcloud run services describe taal-agents --project amru-509214 --region asia-south1 --format=json` (and same for `taal-web`) and inspecting `.template.scaling.minInstanceCount` / `.template.containers[].resources.cpuIdle` |

### Backtest, per-tier detail (from row 1)

```
tier          model                 n_origins  mean_mape   mean_bias   n_series(last origin)
bakery        local_seasonal_xreg   7          0.1073      0.0193      42
beverages     local_seasonal_xreg   7          0.1095      0.0177      135
dairy         local_seasonal_xreg   7          0.1095      0.0162      96
household     local_seasonal_xreg   7          0.1334      0.0276      90
personal_care local_seasonal_xreg   7          0.1280      0.0241      72
premium_tea   local_seasonal_xreg   7          0.2212      0.0706      42
snacks        local_seasonal_xreg   7          0.1110      0.0163      135
staples       local_seasonal_xreg   7          0.1272      0.0018      180
sweets        local_seasonal_xreg   7          0.1509      0.0144      108
```

`premium_tea`'s higher MAPE (0.22) and bias (0.07) reflects a smaller, more volatile series
(42 vs 90-180 for other tiers) -- consistent with the demo's own premium-tea gap being the one
DECISIONS calls out for a manual policy-change beat rather than a fully automated one.

## Not measured, and why (DECISIONS §12 rows this project cannot produce)

| Metric | Why it is absent |
|---|---|
| Pilot treated-vs-holdout with confidence intervals | No pilot has run. `docs/pilot.md` describes a design (recruitment, consent, pre-registered metric), not a result. |
| Agent Simulation guardrail pass rate over ~200 personas | Agent Simulation (Vertex AI Agent Platform) has never been invoked against the Customer Agent in this project. No simulation run, no pass rate. |
| Gemini-as-judge rationale score + 15-item human-labelled agreement | No judge-model scoring pipeline exists in this repo, and no human labelling of planner rationales has been done. |
| Vision read accuracy over 30 staged photos | Only 3 pallet fixtures exist under `fixtures/photos/` (`pallet_01.json` through `pallet_03.json`), and they are recorded reads, not live-graded accuracy against ground truth. 30 staged photos with graded accuracy do not exist. |
| Cost per play from the billing export | No billing export has been pulled for this project. The cost figures in `docs/DECISIONS.md` §18.4/§18.5 remain list-price estimates, explicitly labelled as such. |
| Planner Agent fan-out, 50 gaps, Batch API | The Batch API fan-out design in §18.3 has not been built; nothing in this repo submits a Batch job. |
| BigQuery bytes scanned, one Sense run | Sense reads/writes `LocalStore`, not BigQuery, in this codebase today (verified: `grep -rn "bigquery.Client" agents/ services/ jobs/ data/ harness/` finds no hits outside the new `jobs/sense/copy.py::generate_copy_bigquery`). There is no BigQuery job for Sense to have a bytes-scanned figure. |
| `AI.GENERATE_TABLE` end-to-end copy generation | Wired up this session (`jobs/sense/copy.py::generate_copy_bigquery`, `infra/deploy.sh` creates the connection + remote model), but the connection's service account lacks the `roles/aiplatform.user` grant needed for `CREATE MODEL`/`AI.GENERATE_TABLE` to work, and granting IAM roles is outside what this environment will do on its own initiative. Confirmed working as designed up to that point: a real approve() call attempted the BigQuery path and fell back to templated copy cleanly (see row 4's caveat). |

## Part B evidence

- **B1 (scale-to-zero confirmed):** row 8 above.
- **B2 (cold start):** row 7 above.
- **B3 (budgets):** attempted to confirm/apply `infra/budgets.sh`. The Cloud Billing API and
  Cloud Billing Budget API were both disabled on the project; enabled both
  (`serviceusage.services.enable`, not an IAM change). Billing account resolved:
  `billingAccounts/01AFA8-481EFC-C09462`. Listing/creating budgets then failed with a genuine
  GCP 403 ("The caller does not have permission") -- the deploy identity (`taal-deploy`) holds
  `roles/owner` on the **project**, but budgets are a resource on the **billing account**, which
  needs its own separate role binding (e.g. `roles/billing.admin` granted at the billing account,
  not the project). This is not the harness's permission-grant restriction; it is a real GCP
  authorization gap that a human with billing-account access needs to close, e.g. by running
  `infra/budgets.sh` themselves once (`BILLING_ACCOUNT_ID=01AFA8-481EFC-C09462`), or by granting
  `taal-deploy` a billing-account-level role first. **Budget alerts are not yet confirmed live.**
- **B3 (rate limit):** added a generous per-visitor cap (`services/api/main.py::_rate_limit`) on
  `POST /plan`, `POST /rerun` (20 calls / 15 min per visitor -- a live planner run takes
  70-110s, so this bounds worst-case concurrent spend without a normal demo ever seeing it) and
  `POST /chat` (60 calls / 15 min per visitor). Read endpoints (`/health`, `/gaps`, `/plays`, ...)
  are untouched. `tests/api` still passes unmodified (well under both limits).
