#!/usr/bin/env bash
# infra/iam.sh -- least-privilege service accounts for the three services (DECISIONS §17.3
# "Infra and deploy: IAM matrix applied"). Idempotent.
#
# Requires: GOOGLE_CLOUD_PROJECT
set -euo pipefail

: "${GOOGLE_CLOUD_PROJECT:?set GOOGLE_CLOUD_PROJECT}"
PROJECT="${GOOGLE_CLOUD_PROJECT}"

create_sa() {
  local name="$1" display="$2"
  gcloud iam service-accounts create "${name}" \
    --project "${PROJECT}" --display-name "${display}" \
    2>/dev/null || echo "   (service account ${name} already exists)"
}

bind_role() {
  local name="$1" role="$2"
  gcloud projects add-iam-policy-binding "${PROJECT}" \
    --member "serviceAccount:${name}@${PROJECT}.iam.gserviceaccount.com" \
    --role "${role}" \
    --condition=None \
    >/dev/null
}

echo "== creating service accounts =="
create_sa taal-agents "Taal agents (Planner, Customer, Vision, Approve)"
create_sa taal-sense  "Taal Sense nightly job"
create_sa taal-web    "Taal web frontend"

echo "== binding roles: taal-agents =="
bind_role taal-agents roles/bigquery.dataEditor
bind_role taal-agents roles/bigquery.jobUser
bind_role taal-agents roles/datastore.user
bind_role taal-agents roles/aiplatform.user

echo "== binding roles: taal-sense =="
bind_role taal-sense roles/bigquery.dataEditor
bind_role taal-sense roles/bigquery.jobUser
bind_role taal-sense roles/datastore.user

echo "== binding roles: taal-web =="
# taal-web needs no BigQuery/Firestore/Vertex role of its own -- it only calls taal-agents over
# HTTP. Grant it invoker on that service specifically (least privilege, not a project-wide role).
gcloud run services add-iam-policy-binding taal-agents \
  --project "${PROJECT}" --region "${REGION:-asia-south1}" \
  --member "serviceAccount:taal-web@${PROJECT}.iam.gserviceaccount.com" \
  --role roles/run.invoker \
  >/dev/null || echo "   (taal-agents not deployed yet; run infra/deploy.sh first, then re-run this)"

echo
echo "== IAM matrix =="
printf "%-14s %-28s %s\n" "SERVICE" "ROLE" "SCOPE"
printf "%-14s %-28s %s\n" "taal-agents" "roles/bigquery.dataEditor" "project"
printf "%-14s %-28s %s\n" "taal-agents" "roles/bigquery.jobUser" "project"
printf "%-14s %-28s %s\n" "taal-agents" "roles/datastore.user" "project"
printf "%-14s %-28s %s\n" "taal-agents" "roles/aiplatform.user" "project"
printf "%-14s %-28s %s\n" "taal-sense" "roles/bigquery.dataEditor" "project"
printf "%-14s %-28s %s\n" "taal-sense" "roles/bigquery.jobUser" "project"
printf "%-14s %-28s %s\n" "taal-sense" "roles/datastore.user" "project"
printf "%-14s %-28s %s\n" "taal-web" "roles/run.invoker" "taal-agents service only"
