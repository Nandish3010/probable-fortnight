# Development and deploy

Moved from the README on 14 Oct 2026. The README keeps one line and a link.

## Development

```
make setup      # uv sync + npm ci
make verify     # secrets -> lint -> schemas -> generate -> unit -> sql -> agents -> api-test -> web-test -> docs -> status
make api        # FastAPI on :8080 against .local/data
make web        # Next.js on :3000 (NEXT_PUBLIC_TAAL_MOCK=1 for fixtures only)
make fixtures   # rebuild committed golden plays, mutations, golden runs, evalsets
make openapi    # regenerate docs/openapi.yaml
```

Green `make verify` (470+ pytest and 490+ Playwright tests, the CI gate in `.github/workflows/verify.yml`) is the only definition of done. Specs and design: `docs/DECISIONS.md`, `docs/DATA_MODEL.md`, `docs/architecture.md`, `docs/scale.md`, `docs/pilot.md`, `docs/privacy.md`, `docs/openapi.yaml`.

## Make targets

Taken from the `##` comments in the `Makefile` on 14 Oct 2026; the Makefile is the source of truth.

| Target | What it does |
|---|---|
| `make setup` | install python + web deps |
| `make verify` | full harness; stops at first red |
| `make secrets` | no credentials, no attribution trailers, no raw data |
| `make schemas` | schema validity, golden/mutated plays, model<->schema sync |
| `make generate` | seeded tenant -> Sense -> demo plays -> flagship prior update (SYNTHETIC) into $(TAAL_DATA_DIR); determinism checked in tests |
| `make fixtures` | rebuild committed fixtures (golden plays, mutations, golden runs, evalsets) from the tenant |
| `make mocks` | regenerate web/mocks/*.json from the API (after make generate) |
| `make openapi` | regenerate docs/openapi.yaml from the FastAPI app |
| `make ingest-roundtrip` | seeded tenant -> contract CSVs -> data.ingest -> Sense; gaps must be identical (eval/raw/ingest_roundtrip_<date>/) |
| `make samples` | rebuild data/samples/*.csv (the ingest contract's worked example) from the seeded tenant |
| `make sense` | nightly job locally |
| `make backtest` | rolling-origin forecast backtest on the sample slice -> eval_forecast |
| `make measure` | measure job locally |
| `make unit` | gate, estimator, assignment, sellby (unit + property tests) |
| `make sql` | DDL + assertions on a local DuckDB built from generated data |
| `make agents` | stub-mode planner evalset + scripted customer conversations |
| `make api-test` | FastAPI contract tests against openapi.yaml |
| `make web-test` | typecheck + Playwright judge-mode tests in mock mode (skips if web/node_modules missing) |
| `make docs` | README/docs lint: links, quick-start card first, required sections; deck claims cite paths that exist |
| `make status` | regenerate STATUS.md from checklists + test results |
| `make feedback-summary` | real practitioner feedback -> eval/raw/feedback_summary_<date>/summary.{json,md}; exclusions in config/feedback_exclusions.json (TAAL_FEEDBACK_STORE picks the store, or pass ARGS="--export file") |
| `make vision-real-prep` | real phone photos in .local/photos -> EXIF-stripped, downscaled copies under VISION_REAL_DIR (EXCLUDE=a.jpg,b.jpg) |
| `make vision-real-eval` | live Vertex vision accuracy on VISION_REAL_DIR, 3 passes -> results.json + summary.md there |
| `make nightly-report` | read-only nightly Sense/Measure record -> eval/raw/nightly_runs/<date>.json + README row (needs GOOGLE_APPLICATION_CREDENTIALS) |
| `make eval-table` | regenerate eval/evaluation_table.md from eval/evaluation.md + eval/raw/ (never typed by hand) |
| `make api` | run the local API against fixtures |
| `make live-test` | persona walkthrough against a running `make api` + `make web` (screenshots in eval/runs/screens) |
| `make sweep` | every API endpoint, one line each, against API (default local; pass API=https://... for Cloud Run) |
| `make demo` | local demo = api + web against generated data |
| `make eval-gaps` | pick the 50 planner evalset gaps (stratified) -> eval/raw/planner_evalset_selection_<date>.json |
| `make planner-traces` | one recorded planner run per selected gap -> eval/raw/planner_traces_<date>/ (set TAAL_MODEL_BACKEND=vertex) |
| `make pregenerate-copy` | demo plays' offer copy via BigQuery AI.GENERATE_TABLE -> fixtures/copy_pregenerated.json (set TAAL_MODEL_BACKEND=vertex, GOOGLE_CLOUD_PROJECT; run `make generate` first) |
| `make eval` | planner evalset (stub or vertex per TAAL_MODEL_BACKEND) |
| `make deck` | render deck/slides.html -> docs/deck.pdf (18 pages) and deck/png/slide_NN.png (needs `make setup`) |
| `make deploy` | gcloud scripts under infra/ (require GOOGLE_CLOUD_PROJECT) |

## CI and deploy runbook

- `.github/workflows/verify.yml` runs `make verify` on every pull request and every push to `main`. A second job, `live-test`, starts `make api` and `make web` and runs the persona walkthrough (`make live-test`) against the real stack.
- Only a push to `main` deploys: after `verify` is green, the `deploy` job runs `infra/deploy.sh` (Cloud Run services `taal-agents` and `taal-web`, the nightly `taal-sense` and `taal-measure` jobs, BigQuery DDL), then the `smoke` job runs `infra/smoke_test.sh` against the live URLs (health, a real gap, a real approve, a real chat reply). A red smoke fails the pipeline.
- Script order, required environment variables, IAM and the current deployment (`amru-509214`, `asia-south1`): [`infra/README.md`](../infra/README.md).
- Cold starts: `min-instances` is 0 on both services (`infra/min_instances.sh on|off` raises or lowers it for a demo window). On 13 Oct two Cloud Scheduler keep-warm jobs were added, `taal-agents-warm` (every 5 minutes) and `taal-web-keepwarm` (every 10 minutes); they ping the services so an instance is usually warm, and min-instances stays 0.
- `taal-agents` runs with `--max-instances 1` (`infra/deploy.sh`) because each visitor's sandbox is on the instance's local disk and re-plan run state is in process memory; see [`scale.md`](scale.md).

## Specs and design documents

[`DECISIONS.md`](DECISIONS.md), [`DATA_MODEL.md`](DATA_MODEL.md), [`architecture.md`](architecture.md), [`scale.md`](scale.md), [`pilot.md`](pilot.md), [`privacy.md`](privacy.md), [`openapi.yaml`](openapi.yaml).
