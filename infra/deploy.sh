#!/usr/bin/env bash
# infra/deploy.sh -- deploy Taal to a Google Cloud project (DECISIONS §4, §4.4, §17.3 "Infra and
# deploy"). Idempotent: safe to re-run. No secrets are written or read by this script directly;
# runtime secrets live in Secret Manager (created out of band) and are referenced by name only.
#
# Requires:
#   GOOGLE_CLOUD_PROJECT   the target project id
#   REGION                 e.g. asia-south1 (fallback asia-southeast1 or us -- see infra/README.md)
#
# Usage: GOOGLE_CLOUD_PROJECT=my-proj REGION=asia-south1 ./infra/deploy.sh
set -euo pipefail

# ---- chat-time Google Cloud integrations on taal-agents (rollback = set back to 0 and redeploy) ----
# Vertex AI Sessions (Agent Engine) for chat sessions, keyed per visitor + customer
# (agents/chat_runtime.py::adk_ids). 0 = in-memory sessions, today's behaviour.
ENABLE_VERTEX_SESSIONS=0
# The Agent Engine created and verified in eval/raw/vertex_sessions_2026-09-24/summary.json.
AGENT_ENGINE_ID=5616208637656563712
# Firestore serving cache for stock + customer profiles (agents/gate/firestore_cache.py), mirrored
# from the image's own seeded snapshot by the taal-cache-mirror job below. 0 = every chat read goes
# to the visitor's store, today's behaviour.
ENABLE_SERVING_CACHE=0
# Both stay 0 until the live acceptance runs (p95 < 6.0 s over 50 /chat calls, restart test)
# are committed under eval/raw/ -- see eval/evaluation.md, "Sessions and serving cache".

: "${GOOGLE_CLOUD_PROJECT:?set GOOGLE_CLOUD_PROJECT}"
: "${REGION:?set REGION}"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT="${GOOGLE_CLOUD_PROJECT}"
DATASET="taal"

echo "== Taal deploy: project=${PROJECT} region=${REGION} =="

echo "-- enabling APIs --"
gcloud services enable \
  run.googleapis.com \
  bigquery.googleapis.com \
  firestore.googleapis.com \
  aiplatform.googleapis.com \
  cloudscheduler.googleapis.com \
  secretmanager.googleapis.com \
  --project "${PROJECT}"

echo "-- creating BigQuery dataset ${DATASET} in ${REGION} (no-op if it exists) --"
bq --project_id="${PROJECT}" mk --dataset --location="${REGION}" "${PROJECT}:${DATASET}" || true

echo "-- applying DDL, in order --"
for f in "${ROOT_DIR}"/data/bigquery/ddl/*.sql; do
  echo "   applying $(basename "${f}")"
  bq query --project_id="${PROJECT}" --use_legacy_sql=false < "${f}"
done

# `CREATE TABLE IF NOT EXISTS` above never alters an existing table's schema -- an already-live
# `taal.gaps` keeps whatever `evidence` fields it had the day it was first created, however far
# 14_gaps.sql's own STRUCT has moved on since. Found live 2026-09-27: jobs/sense/gaps.py emits
# evidence keys for online_sellby_breach/expiry_writeoff, stockout_risk, slow_mover, unmet_demand
# and assortment_gap gaps that 14_gaps.sql's STRUCT had never declared, so writing any of those
# gap types to BigQuery failed the moment it was first tried for real. This is the additive
# migration step for exactly that: it never drops, renames or retypes a field, only adds ones
# that are missing. CI has `bq` but no Python packages, so the patch is stdlib-only.
echo "-- migrating taal.gaps.evidence (additive nested fields only) --"
bq show --schema --format=prettyjson "${PROJECT}:${DATASET}.gaps" > /tmp/gaps_schema.json
python3 - "${PROJECT}" "${DATASET}" <<'PYEOF'
import json, subprocess, sys

project, dataset = sys.argv[1], sys.argv[2]
# Keep this in sync with data/bigquery/ddl/14_gaps.sql's evidence STRUCT -- any field added there
# for a new gap-evidence key must be added here too, or a fresh `CREATE TABLE IF NOT EXISTS` and
# this migration step will disagree with each other on what "the schema" is.
REQUIRED = [
    ("expiry_date", "STRING", "NULLABLE"),
    ("online_sellby_date", "STRING", "NULLABLE"),
    ("sellby_passed", "BOOLEAN", "NULLABLE"),
    ("sku_name", "STRING", "NULLABLE"),
    ("category", "STRING", "NULLABLE"),
    ("node_type", "STRING", "NULLABLE"),
    ("lead_time_days", "INTEGER", "NULLABLE"),
    ("velocity_per_day", "FLOAT", "NULLABLE"),
    ("category_median_velocity", "FLOAT", "NULLABLE"),
    ("slow_mover_days", "INTEGER", "NULLABLE"),
    ("requesting_customer_ids", "STRING", "REPEATED"),
    ("supply_node_id", "STRING", "NULLABLE"),
    ("garment_type", "STRING", "NULLABLE"),
    ("colour_family", "STRING", "NULLABLE"),
    ("counterpart_gap_id", "STRING", "NULLABLE"),
]

with open("/tmp/gaps_schema.json") as f:
    schema = json.load(f)

evidence = next(f for f in schema if f["name"] == "evidence")
existing = {f["name"] for f in evidence["fields"]}
added = []
for name, field_type, mode in REQUIRED:
    if name not in existing:
        entry = {"name": name, "type": field_type, "mode": mode}
        evidence["fields"].append(entry)
        added.append(name)

if added:
    print(f"   adding evidence fields: {added}")
    with open("/tmp/gaps_schema_patched.json", "w") as f:
        json.dump(schema, f, indent=2)
    subprocess.run(["bq", "update", f"{project}:{dataset}.gaps", "/tmp/gaps_schema_patched.json"], check=True)
    print("   taal.gaps schema updated")
else:
    print("   taal.gaps.evidence already has every required field; no-op")
PYEOF

# The model id lives only in config/models.toml -- resolved here with Python's stdlib TOML
# parser (3.11+) so it is never hardcoded into a script or a .sql file. Copy generation uses
# `ids.flash`, not `ids.flash_lite`: flash_lite 404s in asia-south1 (verified 20 Sep 2026; see
# config/models.toml), and moving the dataset to us-central1 to keep flash-lite was judged not
# worth it (services/api/README or infra/README has the reasoning).
COPY_MODEL="$(python3 -c "import tomllib; print(tomllib.load(open('${ROOT_DIR}/config/models.toml','rb'))['ids']['flash'])")"
# BigQuery splits a single backtick-quoted identifier on '.', so a model id with dots in it
# (gemini-2.5-flash) mis-parses `taal.gemini-2.5-flash_remote` as more path segments than
# intended -- confirmed by actually running this CREATE MODEL statement and reading the error
# ("Dataset ...taal.gemini-2 was not found"), not guessed. Sanitize the resource name; the
# literal id still goes into OPTIONS(endpoint=...) unsanitized, matching jobs/sense/copy.py.
COPY_MODEL_RESOURCE="${COPY_MODEL//./_}_remote"
CONNECTION_ID="taal_vertex"

echo "-- creating the BigQuery <-> Vertex AI connection ${CONNECTION_ID} (no-op if it exists) --"
bq --project_id="${PROJECT}" mk --connection --connection_type=CLOUD_RESOURCE --location="${REGION}" "${CONNECTION_ID}" 2>/dev/null || true
CONNECTION_SA="$(bq --project_id="${PROJECT}" show --connection --location="${REGION}" --format=json "${CONNECTION_ID}" | python3 -c "import json,sys; print(json.load(sys.stdin)['cloudResource']['serviceAccountId'])")"
echo "   connection service account: ${CONNECTION_SA}"

echo "-- granting the connection's service account Vertex AI User (idempotent) --"
gcloud projects add-iam-policy-binding "${PROJECT}" \
  --member="serviceAccount:${CONNECTION_SA}" \
  --role="roles/aiplatform.user" \
  --condition=None \
  --quiet >/dev/null

echo "-- creating the remote model \`${DATASET}.${COPY_MODEL_RESOURCE}\` over ${COPY_MODEL} (no-op if it already matches) --"
# The IAM grant above is eventually consistent -- BigQuery's cross-service permission check for
# the connection's service account can reject this query for up to a minute or two after
# add-iam-policy-binding returns success (confirmed live: a fresh grant, then this query 3s
# later, failed with "does not have the permission to access or use the endpoint" even though
# the binding was already in the policy). Retry instead of failing the whole deploy on it.
for attempt in 1 2 3 4 5 6; do
  if bq query --project_id="${PROJECT}" --use_legacy_sql=false <<SQL
CREATE OR REPLACE MODEL \`${PROJECT}\`.\`${DATASET}\`.\`${COPY_MODEL_RESOURCE}\`
REMOTE WITH CONNECTION \`${PROJECT}.${REGION}.${CONNECTION_ID}\`
OPTIONS (endpoint = '${COPY_MODEL}');
SQL
  then
    break
  elif [ "${attempt}" -eq 6 ]; then
    echo "remote model creation still failing after IAM propagation retries" >&2
    exit 1
  else
    echo "   IAM grant likely still propagating; retrying in 20s (attempt ${attempt}/6)"
    sleep 20
  fi
done

echo "-- building and deploying taal-agents (services/api) --"
gcloud builds submit "${ROOT_DIR}" \
  --project "${PROJECT}" \
  --config /dev/stdin \
  --substitutions=_IMAGE="${REGION}-docker.pkg.dev/${PROJECT}/taal/taal-agents" <<'EOF'
steps:
  - name: gcr.io/cloud-builders/docker
    args: ['build', '-f', 'infra/Dockerfile.api', '-t', '${_IMAGE}', '.']
images: ['${_IMAGE}']
EOF

# Practitioner feedback: real answers go to their own Firestore collections (never the container
# disk), so the database has to exist before taal-agents takes traffic. No-op when it already does.
echo "-- ensuring the Firestore (default) database exists for practitioner feedback --"
if ! gcloud firestore databases describe --database="(default)" --project "${PROJECT}" >/dev/null 2>&1; then
  gcloud firestore databases create --database="(default)" --location="${REGION}" --type=firestore-native --project "${PROJECT}" \
    || echo "   WARNING: could not create or see the Firestore database; feedback_smoke.sh at the end will say whether writes work"
fi

# The admin token for /feedback/summary and DELETE /feedback/{id} lives only in Secret Manager.
# Created here once, from random bytes that never touch the log or the repo; read it back with
#   gcloud secrets versions access latest --secret taal-feedback-admin-token --project <project>
# Best effort: if this identity may not create or read secrets, submissions still work and only
# the results page and deletion answer 503 until someone creates it by hand.
FEEDBACK_SECRET="taal-feedback-admin-token"
if ! gcloud secrets describe "${FEEDBACK_SECRET}" --project "${PROJECT}" >/dev/null 2>&1; then
  echo "   creating secret ${FEEDBACK_SECRET}"
  python3 -c "import secrets; print(secrets.token_hex(32), end='')" \
    | gcloud secrets create "${FEEDBACK_SECRET}" --data-file=- --replication-policy=automatic --project "${PROJECT}" \
    || echo "   WARNING: could not create ${FEEDBACK_SECRET}; /feedback/results will be disabled"
fi
FEEDBACK_SECRET_FLAG=()
if gcloud secrets describe "${FEEDBACK_SECRET}" --project "${PROJECT}" >/dev/null 2>&1; then
  # The runtime identity of taal-agents (the Compute default service account unless a
  # --service-account was set on the service) must be able to read the secret at startup.
  RUNTIME_SA="$(gcloud run services describe taal-agents --project "${PROJECT}" --region "${REGION}" --format='value(spec.template.spec.serviceAccountName)' 2>/dev/null || true)"
  if [ -z "${RUNTIME_SA}" ]; then
    RUNTIME_SA="$(gcloud projects describe "${PROJECT}" --format='value(projectNumber)' || true)-compute@developer.gserviceaccount.com"
  fi
  if gcloud secrets add-iam-policy-binding "${FEEDBACK_SECRET}" --project "${PROJECT}" \
      --member "serviceAccount:${RUNTIME_SA}" --role roles/secretmanager.secretAccessor >/dev/null; then
    FEEDBACK_SECRET_FLAG=(--update-secrets "TAAL_FEEDBACK_ADMIN_TOKEN=${FEEDBACK_SECRET}:latest")
  else
    echo "   WARNING: could not grant ${RUNTIME_SA} access to ${FEEDBACK_SECRET}; /feedback/results will be disabled"
  fi
else
  echo "   (secret ${FEEDBACK_SECRET} not found: /feedback/results will be disabled)"
fi

AGENTS_ENV="TAAL_MODEL_BACKEND=vertex,TAAL_TENANT_CONFIG=config/tenant.demo.toml,GOOGLE_CLOUD_PROJECT=${PROJECT},TAAL_FEEDBACK_STORE=firestore,TAAL_PLANNER_DEADLINE_S=45"
if [ "${ENABLE_VERTEX_SESSIONS}" = "1" ]; then
  echo "   chat sessions: Vertex AI Sessions on Agent Engine ${AGENT_ENGINE_ID}"
  AGENTS_ENV="${AGENTS_ENV},TAAL_SESSION_BACKEND=vertex,TAAL_AGENT_ENGINE_ID=${AGENT_ENGINE_ID},TAAL_REGION=${REGION}"
fi
if [ "${ENABLE_SERVING_CACHE}" = "1" ]; then
  echo "   chat reads: Firestore serving cache (mirrored below from this image's snapshot)"
  AGENTS_ENV="${AGENTS_ENV},TAAL_SERVING_CACHE=firestore"
fi
gcloud run deploy taal-agents \
  --project "${PROJECT}" --region "${REGION}" \
  --image "${REGION}-docker.pkg.dev/${PROJECT}/taal/taal-agents" \
  --set-env-vars "${AGENTS_ENV}" \
  ${FEEDBACK_SECRET_FLAG[@]+"${FEEDBACK_SECRET_FLAG[@]}"} \
  --allow-unauthenticated
# CORS: TAAL_ALLOWED_ORIGINS is set at the end of this script, once taal-web's URLs are known.
# (--set-env-vars above replaces every env var, so the origins must be re-applied on each deploy.)

# Serving-cache mirror: from the SAME seeded snapshot and TAAL_NOW the taal-agents image serves
# (the Dockerfile bakes both), as a one-off job on that image -- never from the nightly BigQuery
# job, whose dates are real ones. Idempotent: every doc is a full set keyed by id, and serving
# rejects any doc whose as_of/snapshot_id does not match the image, so a stale mirror degrades to
# store reads, never to wrong answers.
if [ "${ENABLE_SERVING_CACHE}" = "1" ]; then
  echo "-- mirroring the served snapshot into the Firestore serving cache (taal-cache-mirror job) --"
  gcloud run jobs deploy taal-cache-mirror \
    --project "${PROJECT}" --region "${REGION}" \
    --image "${REGION}-docker.pkg.dev/${PROJECT}/taal/taal-agents" \
    --command uv \
    --args="run,python,-m,agents.gate.firestore_cache,--mirror" \
    --set-env-vars "TAAL_TENANT_CONFIG=config/tenant.demo.toml,GOOGLE_CLOUD_PROJECT=${PROJECT}" \
    --execute-now --wait
fi

AGENTS_URL="$(gcloud run services describe taal-agents --project "${PROJECT}" --region "${REGION}" --format='value(status.url)')"
echo "   taal-agents URL: ${AGENTS_URL}"

echo "-- building and deploying taal-web (web) --"
# NEXT_PUBLIC_TAAL_API_URL is inlined into the client bundle at build time, so taal-agents must
# already be deployed before this image is built.
gcloud builds submit "${ROOT_DIR}" \
  --project "${PROJECT}" \
  --config /dev/stdin \
  --substitutions=_IMAGE="${REGION}-docker.pkg.dev/${PROJECT}/taal/taal-web",_API_URL="${AGENTS_URL}" <<'EOF'
steps:
  - name: gcr.io/cloud-builders/docker
    args: ['build', '-f', 'infra/Dockerfile.web', '--build-arg', 'NEXT_PUBLIC_TAAL_API_URL=${_API_URL}', '-t', '${_IMAGE}', '.']
images: ['${_IMAGE}']
EOF

gcloud run deploy taal-web \
  --project "${PROJECT}" --region "${REGION}" \
  --image "${REGION}-docker.pkg.dev/${PROJECT}/taal/taal-web" \
  --allow-unauthenticated

# Let the deployed web app call the API from the browser. Cloud Run serves a service at more than
# one URL (the hash form and the project-number form); allow every one it lists. Without this the
# API only accepts localhost origins, and every browser POST -- the feedback form included -- fails.
WEB_ORIGINS="$(gcloud run services describe taal-web --project "${PROJECT}" --region "${REGION}" --format=json \
  | python3 -c "import json,sys; d=json.load(sys.stdin); urls=json.loads(d['metadata'].get('annotations',{}).get('run.googleapis.com/urls','[]')); urls.append(d['status']['url']); print(','.join(sorted(set(u.rstrip('/') for u in urls))))")"
echo "   taal-web origins: ${WEB_ORIGINS}"
gcloud run services update taal-agents \
  --project "${PROJECT}" --region "${REGION}" \
  --update-env-vars "^@^TAAL_ALLOWED_ORIGINS=${WEB_ORIGINS}"


echo "-- building taal-sense image and deploying the Cloud Run Job --"
gcloud builds submit "${ROOT_DIR}" \
  --project "${PROJECT}" \
  --config /dev/stdin \
  --substitutions=_IMAGE="${REGION}-docker.pkg.dev/${PROJECT}/taal/taal-sense" <<'EOF'
steps:
  - name: gcr.io/cloud-builders/docker
    args: ['build', '-f', 'infra/Dockerfile.api', '-t', '${_IMAGE}', '.']
images: ['${_IMAGE}']
EOF

# TAAL_BATCH_STORE and TAAL_FORECAST_BACKEND are set on the taal-sense job's own environment
# only (jobs/sense/run.py::build_batch_store, jobs/measure/run.py::build_batch_store both default
# to 'local' everywhere else, including taal-agents' judge-mode serving path, which keeps reading
# the frozen pinned-clock snapshot and is never switched to BigQuery). This is the nightly-batch
# path from data/bigquery/sense/02_forecast_timesfm.sql -- see eval/raw/bigquery_billing_dml_2026-09-27/
# for the write side of this path (any BigQueryStore.write() call, and 04_rolldown.sql's own
# DELETE): a billing/payment issue on amru-509214 briefly blocked all BigQuery writes on
# 2026-09-27, since resolved. This whole script depends on billing being enabled and current --
# Cloud Build and Cloud Run both require it too, not just this job's BigQuery writes -- so a
# lapsed billing account fails the deploy well before this job runs, not just at its run time.
gcloud run jobs deploy taal-sense \
  --project "${PROJECT}" --region "${REGION}" \
  --image "${REGION}-docker.pkg.dev/${PROJECT}/taal/taal-sense" \
  --command python \
  --args="-m,jobs.sense" \
  --set-env-vars "TAAL_MODEL_BACKEND=vertex,TAAL_TENANT_CONFIG=config/tenant.demo.toml,GOOGLE_CLOUD_PROJECT=${PROJECT},TAAL_BATCH_STORE=bigquery,TAAL_FORECAST_BACKEND=bigquery_timesfm"

echo "-- creating the nightly Cloud Scheduler trigger (01:30 IST = 20:00 UTC) --"
# The oauth-service-account-email must be a real, existing service account or `jobs create`
# fails outright with NOT_FOUND (not "already exists" -- the `|| echo` fallback below used to
# mask this). `taal-sense@${PROJECT}.iam.gserviceaccount.com` was never created (see the "Known
# deviation" note in infra/README.md: iam.sh's three dedicated service accounts need
# roles/iam.serviceAccountAdmin, which taal-deploy does not hold), so this used taal-deploy's own
# identity instead, matching every other resource this script deploys under taal-deploy today.
gcloud scheduler jobs create http taal-sense-nightly \
  --project "${PROJECT}" --location "${REGION}" \
  --schedule "0 20 * * *" \
  --uri "https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT}/jobs/taal-sense:run" \
  --http-method POST \
  --oauth-service-account-email "taal-deploy@${PROJECT}.iam.gserviceaccount.com" \
  || echo "   (scheduler job already exists; run 'gcloud scheduler jobs update' to change it)"

echo "-- building taal-measure image and deploying the Cloud Run Job (same image as taal-sense) --"
gcloud builds submit "${ROOT_DIR}" \
  --project "${PROJECT}" \
  --config /dev/stdin \
  --substitutions=_IMAGE="${REGION}-docker.pkg.dev/${PROJECT}/taal/taal-measure" <<'EOF'
steps:
  - name: gcr.io/cloud-builders/docker
    args: ['build', '-f', 'infra/Dockerfile.api', '-t', '${_IMAGE}', '.']
images: ['${_IMAGE}']
EOF

gcloud run jobs deploy taal-measure \
  --project "${PROJECT}" --region "${REGION}" \
  --image "${REGION}-docker.pkg.dev/${PROJECT}/taal/taal-measure" \
  --command python \
  --args="-m,jobs.measure" \
  --set-env-vars "TAAL_MODEL_BACKEND=vertex,TAAL_TENANT_CONFIG=config/tenant.demo.toml,GOOGLE_CLOUD_PROJECT=${PROJECT},TAAL_BATCH_STORE=bigquery"

echo "-- creating the taal-measure-nightly Cloud Scheduler trigger (30 min after Sense: 02:00 IST = 20:30 UTC) --"
# Same fix as taal-sense-nightly above: taal-sense@ was never created, so this job's create call
# failed NOT_FOUND on every deploy (never actually created, just silently reported as "already
# exists"), which is why the post-deploy verification below always failed on this trigger.
gcloud scheduler jobs create http taal-measure-nightly \
  --project "${PROJECT}" --location "${REGION}" \
  --schedule "30 20 * * *" \
  --uri "https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT}/jobs/taal-measure:run" \
  --http-method POST \
  --oauth-service-account-email "taal-deploy@${PROJECT}.iam.gserviceaccount.com" \
  || echo "   (scheduler job already exists; run 'gcloud scheduler jobs update' to change it)"

# Post-deploy check: fails the deploy if either nightly job or trigger is missing (style of
# infra/feedback_smoke.sh). Deliberately does NOT execute taal-sense or taal-measure -- running
# the forecasting job on every deploy would bill real BigQuery compute.
echo "-- verifying the taal-sense/taal-measure jobs and their nightly triggers exist --"
for job in taal-sense taal-measure; do
  gcloud run jobs describe "${job}" --project "${PROJECT}" --region "${REGION}" >/dev/null \
    || { echo "MISSING Cloud Run Job: ${job}" >&2; exit 1; }
done
for trig in taal-sense-nightly taal-measure-nightly; do
  gcloud scheduler jobs describe "${trig}" --project "${PROJECT}" --location "${REGION}" >/dev/null \
    || { echo "MISSING Cloud Scheduler trigger: ${trig}" >&2; exit 1; }
done

# Last, so a failure here never skips another service's deploy; it still fails the job.
echo "-- practitioner feedback: prove a submission is stored in Firestore (fails the deploy if not) --"
TAAL_AGENTS_URL="${AGENTS_URL}" TAAL_WEB_ORIGIN="${WEB_ORIGINS%%,*}" GOOGLE_CLOUD_PROJECT="${PROJECT}" \
  bash "${ROOT_DIR}/infra/feedback_smoke.sh"

echo "== deploy complete. Run infra/iam.sh next if service accounts are not yet bound. =="
