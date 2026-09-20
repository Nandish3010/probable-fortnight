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

**IAM: resolved.** `taal-deploy@amru-509214.iam.gserviceaccount.com` was granted `roles/owner` on
20 Sep 2026 (after two earlier attempts at a narrower Vertex role picked the wrong entries --
"AI Platform Editor"/`roles/ml.editor` and "Vertex AI Service Agent"/`roles/aiplatform.serviceAgent`
both sound right but grant unrelated permission sets; the correct one is "Vertex AI User" under
the *Vertex AI* product, not the legacy *AI Platform* one -- search "vertex", not "ai platform", in
the role picker). Verified with a real `generateContent` call, not just a permission check: genuine
200, real model text back.

**Known deviation from `iam.sh`'s design, not yet corrected:** all three services currently run
under the deploy identity (`taal-deploy`, now `roles/owner` -- considerably broader than intended)
rather than their own least-privilege service accounts, because creating new service accounts
needs `roles/iam.serviceAccountAdmin`, which wasn't granted at the time this was deployed. Run
`iam.sh` for real and then redeploy each Cloud Run resource with
`--service-account taal-<name>@amru-509214.iam.gserviceaccount.com` to close this gap, and drop
`taal-deploy` back down from `owner` to the specific admin roles listed in `deploy.sh`/this file's
history, before submission -- `owner` is a deliberate, temporary shortcut, not the end state.

**Model IDs: fixed.** Every ID originally pinned in `config/models.toml` (`gemini-3.8-flash`,
`gemini-3.5-flash-lite`, `gemini-3.1-flash-live-preview`, `gemini-3.7-flash`) was invalid -- none
exist in Vertex's publisher model catalog, confirmed by direct `generateContent` calls, not
assumed. Real availability, checked against this project: `gemini-2.5-flash` responds in
`asia-south1`; `gemini-2.5-flash-lite` and `gemini-2.5-pro` 404 there but respond in `us-central1`
(Vertex model availability is genuinely narrower per-region, exactly the risk DECISIONS §3.3/§4.4
flagged and never checked). `ids.flash` -- the only field any code currently reads
(`agents/planner/agent.py`, `agents/customer/agent.py`, `agents/capture/vision.py`) -- is now
`gemini-2.5-flash`, verified live in `asia-south1`, deployed. `flash_lite`/`live`/`fallback` remain
unwired to any code path; requalify them (region included) before wiring up copy generation or
voice.

**Redeploy gotcha specific to REST/client-library deploys (not `gcloud run deploy`, which is
unaffected):** `Service.update()` via the Cloud Run API silently no-ops if the container image
*tag* string is textually unchanged, even when that tag now resolves to a new digest -- unlike
`gcloud run deploy`, it does not re-resolve mutable tags on update. This looked like a successful
redeploy (no error, a plausible URI printed) while actually still serving the old revision; caught
by checking the live revision's `create_time` and image digest directly rather than trusting the
deploy call's return value. If you ever build tooling around the Cloud Run API instead of the
`gcloud` CLI, always resolve the image to its digest (`repositories.../tags/latest`'s `version`
field in Artifact Registry) before calling `update_service`.

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
