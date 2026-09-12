#!/usr/bin/env bash
# infra/budgets.sh -- budget alerts at $50/$100/$200 (DECISIONS §4.4 "budget alerts at
# $50/$100/$200"). Requires a billing account already linked to the project; creates one budget
# with three threshold rules rather than three separate budgets, since gcloud billing budgets
# takes a list of thresholds per budget.
#
# Requires: GOOGLE_CLOUD_PROJECT, BILLING_ACCOUNT_ID (e.g. 012345-6789AB-CDEF01)
set -euo pipefail

: "${GOOGLE_CLOUD_PROJECT:?set GOOGLE_CLOUD_PROJECT}"
: "${BILLING_ACCOUNT_ID:?set BILLING_ACCOUNT_ID (find with: gcloud billing accounts list)}"
PROJECT="${GOOGLE_CLOUD_PROJECT}"

echo "== creating budget for ${PROJECT} on billing account ${BILLING_ACCOUNT_ID} =="
gcloud billing budgets create \
  --billing-account "${BILLING_ACCOUNT_ID}" \
  --display-name "taal-${PROJECT}" \
  --budget-amount 200USD \
  --threshold-rule=percent=0.25 \
  --threshold-rule=percent=0.50 \
  --threshold-rule=percent=1.00 \
  --filter-projects="projects/${PROJECT}" \
  || echo "   (a budget with this display name may already exist; use 'gcloud billing budgets update' to change thresholds)"

echo "   thresholds fire at USD 50 (25%), USD 100 (50%) and USD 200 (100%) of the 200USD budget."
echo "   Notifications go to the billing account's default recipients (billing admins); wire a"
echo "   Pub/Sub topic + Cloud Function if the team channel should get these directly."
