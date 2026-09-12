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

echo "-- building and deploying taal-web (web) --"
gcloud builds submit "${ROOT_DIR}" \
  --project "${PROJECT}" \
  --config /dev/stdin \
  --substitutions=_IMAGE="${REGION}-docker.pkg.dev/${PROJECT}/taal/taal-web" <<'EOF'
steps:
  - name: gcr.io/cloud-builders/docker
    args: ['build', '-f', 'infra/Dockerfile.web', '-t', '${_IMAGE}', '.']
images: ['${_IMAGE}']
EOF

gcloud run deploy taal-web \
  --project "${PROJECT}" --region "${REGION}" \
  --image "${REGION}-docker.pkg.dev/${PROJECT}/taal/taal-web" \
  --allow-unauthenticated

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
