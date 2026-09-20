# infra

Deployment scripts for Taal (DECISIONS §4, §4.4, §17.3, §18.5). All scripts are `bash`,
`set -euo pipefail`, and read configuration only from environment variables and
`config/tenant.demo.toml` / `config/models.toml` -- no secrets are stored in this directory.

## Region

Default region is `asia-south1` (Mumbai). Fall back to `asia-southeast1` or `us` if a required
service (BigQuery ML model types used by Sense, Agent Engine for Sessions) is not yet available
in `asia-south1` at deploy time -- verify this in the console before the first deploy, per
DECISIONS §3.3 and §4.4. Whichever region is chosen, set `REGION` to the same value for every
script below; a mismatched region between the BigQuery dataset and Cloud Run breaks
cross-service latency assumptions in §4.3.

## Order to run

1. **`iam.sh`** -- creates `taal-agents`, `taal-sense`, `taal-web` service accounts and binds
   least-privilege roles. Requires `GOOGLE_CLOUD_PROJECT`. Safe to re-run; the `taal-web` ->
   `taal-agents` invoker binding needs `taal-agents` to already be deployed, so run this script a
   second time after `deploy.sh` if that binding was skipped on the first pass.
2. **`deploy.sh`** -- enables APIs, creates the `taal` BigQuery dataset in `REGION`, applies every
   file under `data/bigquery/ddl/*.sql` in numeric order, builds and deploys `taal-agents`,
   `taal-web`, and the `taal-sense` Cloud Run Job with its nightly Cloud Scheduler trigger at
   01:30 IST (`0 20 * * *` UTC). Requires `GOOGLE_CLOUD_PROJECT`, `REGION`.
3. **`budgets.sh`** -- budget alerts at $50/$100/$200. Requires `GOOGLE_CLOUD_PROJECT`,
   `BILLING_ACCOUNT_ID`.
4. **`min_instances.sh on`** -- before a demo or the judging window; **`min_instances.sh off`**
   afterwards, to return to scale-to-zero (DECISIONS §4.5, §18.3 lever 5).
5. **`smoke.sh`** -- weekly (or on demand) live-URL health check; wire it into a GitHub Actions
   cron per DECISIONS §17.2. Requires `TAAL_AGENTS_URL`, `TAAL_WEB_URL`.

## What each script needs

| Script | Required env | Notes |
|---|---|---|
| `deploy.sh` | `GOOGLE_CLOUD_PROJECT`, `REGION` | idempotent; re-run after a DDL or code change |
| `Dockerfile.api` | -- | built by `deploy.sh`; also used, with a different `--command`, for the `taal-sense` job image |
| `Dockerfile.web` | -- | built by `deploy.sh` |
| `iam.sh` | `GOOGLE_CLOUD_PROJECT` (and `REGION` for the invoker binding step) | prints the IAM matrix at the end |
| `budgets.sh` | `GOOGLE_CLOUD_PROJECT`, `BILLING_ACCOUNT_ID` | one budget, three threshold rules |
| `min_instances.sh` | `GOOGLE_CLOUD_PROJECT`, `REGION` | `on` or `off`; only touches `taal-agents` and `taal-web` (`taal-sense` is a Job, no min-instances) |
| `smoke.sh` | `TAAL_AGENTS_URL`, `TAAL_WEB_URL` | curls `/health` on each; exits non-zero on failure |

## Current deployment (`amru-509214`, `asia-south1`)

Deployed 20 Sep 2026 via direct Cloud Build/Cloud Run/BigQuery/Firestore API calls (the deploying
environment had no working `gcloud`/`bq` CLI), not literally by running these scripts -- but every
step below matches what `deploy.sh` does, and the two real bugs it surfaced are now fixed in the
scripts themselves, so a future `./infra/deploy.sh` run reproduces this cleanly.

- `taal-agents`: https://taal-agents-2obkp776ca-el.a.run.app
- `taal-web`: https://taal-web-2obkp776ca-el.a.run.app
- `taal-sense`: Cloud Run Job created; nightly Scheduler trigger `taal-sense-nightly` at 01:30 IST
- BigQuery dataset `taal` (all 28 `data/bigquery/ddl/*.sql` files applied), Firestore Native
  database, Artifact Registry repo `taal` -- all in `asia-south1`

**Known deviation from `iam.sh`'s design, not yet corrected:** all three services currently run
under the deploy identity (`taal-deploy@amru-509214.iam.gserviceaccount.com`, an admin-heavy
account) rather than their own least-privilege service accounts, because creating new service
accounts needs `roles/iam.serviceAccountAdmin`, which the deploy identity didn't have at the time.
Run `iam.sh` for real (with a service account that has `iam.serviceAccountAdmin`) and then
redeploy each Cloud Run resource with `--service-account taal-<name>@amru-509214.iam.gserviceaccount.com`
to close this gap before submission.

**Still needed on the `taal-deploy` service account:** `roles/aiplatform.user` -- without it every
Vertex AI/Gemini call from `taal-agents` (Planner, Customer, Capture) will 403. Grant it at
https://console.cloud.google.com/iam-admin/serviceaccounts/details/101345873735082654545/permissions?project=amru-509214
(Edit access -> Add role -> search "Vertex AI User" -- not "AI Platform Editor" and not "Vertex AI
Service Agent", both of which sound right but grant a different, unrelated permission set).

## Deploy gotchas found by actually deploying (fixed here, worth knowing if you touch these files)

1. **`.dockerignore`** (repo root) exists now -- without it, `Dockerfile.api`'s `COPY . .` pulls in
   `.venv`, `web/node_modules`, `.git`, `.local` (1GB+) into every build.
2. **`Dockerfile.api`** runs `uv sync --frozen --no-dev --no-install-project` right after copying
   only `pyproject.toml`/`uv.lock` (fast cached layer, no source yet), then a second
   `uv sync --frozen --no-dev` after `COPY . .`. Reversing this (installing before the source
   tree exists) fails, because the project is a local editable package that needs `agents/` etc.
   present to install itself.
3. **`Dockerfile.web`** creates `public/` before `npm run build` -- the directory is currently
   empty and unused, so git never materializes it (git doesn't track empty directories), and a
   fresh clone hits the same `COPY --from=builder /app/public` failure without this.
4. **`NEXT_PUBLIC_TAAL_API_URL` is a Next.js build-time value**, inlined into the client bundle by
   `next build` -- it is *not* read from the container's runtime environment. `deploy.sh` deploys
   `taal-agents` first, reads its URL back with `gcloud run services describe`, and passes that
   into the `taal-web` Cloud Build as `--build-arg NEXT_PUBLIC_TAAL_API_URL=...`. If you ever
   change `taal-agents`'s URL (a different region, a service rename), `taal-web` must be rebuilt,
   not just redeployed with a new env var.

## Not in this directory

- Secret values (API keys, service-account keys) -- created out of band in Secret Manager and
  referenced by name from the services that need them; `make secrets` in the root harness scans
  for accidental leaks.
- The Vertex AI connection and remote models used by `data/bigquery/sense/07_substitutes.sql` and
  `08_copy.sql` (`taal.text_embedding_model`, `taal.{{FLASH_LITE_MODEL}}_remote`) -- these are
  BigQuery objects created once against a `CREATE CONNECTION` alongside `deploy.sh`'s dataset
  creation step; add that connection step here once the connection id is decided.
