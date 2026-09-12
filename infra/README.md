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

## Not in this directory

- Secret values (API keys, service-account keys) -- created out of band in Secret Manager and
  referenced by name from the services that need them; `make secrets` in the root harness scans
  for accidental leaks.
- The Vertex AI connection and remote models used by `data/bigquery/sense/07_substitutes.sql` and
  `08_copy.sql` (`taal.text_embedding_model`, `taal.{{FLASH_LITE_MODEL}}_remote`) -- these are
  BigQuery objects created once against a `CREATE CONNECTION` alongside `deploy.sh`'s dataset
  creation step; add that connection step here once the connection id is decided.
