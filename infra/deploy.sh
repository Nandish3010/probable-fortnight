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

gcloud run deploy taal-agents \
  --project "${PROJECT}" --region "${REGION}" \
  --image "${REGION}-docker.pkg.dev/${PROJECT}/taal/taal-agents" \
  --set-env-vars "TAAL_MODEL_BACKEND=vertex,TAAL_TENANT_CONFIG=config/tenant.demo.toml,GOOGLE_CLOUD_PROJECT=${PROJECT}" \
  --allow-unauthenticated

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

WEB_URL="$(gcloud run services describe taal-web --project "${PROJECT}" --region "${REGION}" --format='value(status.url)')"
echo "   taal-web URL: ${WEB_URL}"
echo "-- restricting taal-agents CORS to taal-web's URL --"
gcloud run services update taal-agents \
  --project "${PROJECT}" --region "${REGION}" \
  --update-env-vars "TAAL_ALLOWED_ORIGINS=${WEB_URL}"

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

gcloud run jobs deploy taal-sense \
  --project "${PROJECT}" --region "${REGION}" \
  --image "${REGION}-docker.pkg.dev/${PROJECT}/taal/taal-sense" \
  --command python \
  --args="-m,jobs.sense" \
  --set-env-vars "TAAL_MODEL_BACKEND=vertex,TAAL_TENANT_CONFIG=config/tenant.demo.toml,GOOGLE_CLOUD_PROJECT=${PROJECT}"

echo "-- creating the nightly Cloud Scheduler trigger (01:30 IST = 20:00 UTC) --"
gcloud scheduler jobs create http taal-sense-nightly \
  --project "${PROJECT}" --location "${REGION}" \
  --schedule "0 20 * * *" \
  --uri "https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT}/jobs/taal-sense:run" \
  --http-method POST \
  --oauth-service-account-email "taal-sense@${PROJECT}.iam.gserviceaccount.com" \
  || echo "   (scheduler job already exists; run 'gcloud scheduler jobs update' to change it)"

echo "== deploy complete. Run infra/iam.sh next if service accounts are not yet bound. =="
