#!/usr/bin/env bash
# infra/min_instances.sh on|off -- toggle min-instances=1 on the three Cloud Run services for
# demo days (DECISIONS §4.5: "min-instances=1 only from submission to 4 Dec"). taal-sense is a
# Cloud Run Job, not a service, and has no min-instances concept, so this only touches
# taal-agents and taal-web.
#
# Requires: GOOGLE_CLOUD_PROJECT, REGION
# Usage: ./infra/min_instances.sh on
#        ./infra/min_instances.sh off
set -euo pipefail

: "${GOOGLE_CLOUD_PROJECT:?set GOOGLE_CLOUD_PROJECT}"
: "${REGION:?set REGION}"
PROJECT="${GOOGLE_CLOUD_PROJECT}"

MODE="${1:-}"
case "${MODE}" in
  on)  MIN=1 ;;
  off) MIN=0 ;;
  *)   echo "usage: $0 on|off" >&2; exit 1 ;;
esac

for svc in taal-agents taal-web; do
  echo "== setting min-instances=${MIN} on ${svc} =="
  gcloud run services update "${svc}" \
    --project "${PROJECT}" --region "${REGION}" \
    --min-instances "${MIN}"
done

echo "== min-instances=${MIN} applied to taal-agents and taal-web =="
