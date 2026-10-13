#!/usr/bin/env bash
# infra/keepwarm.sh create|pause|resume|delete -- Cloud Scheduler pings that keep the two Cloud Run
# services warm during judging while min-instances stays 0 (owner decision, 11 Oct 2026).
#
#   taal-agents-warm     */5  GET <agents>/health   (created 12 Oct; /health reads the local store and
#                                                     resolves credentials only: no BigQuery, no model call)
#   taal-web-keepwarm    */10 GET <web>/            (the root is a prerendered static page: it hits the
#                                                     Next server but makes no API call; /favicon.ico is a 404)
#
# Both services allow unauthenticated access, so no OIDC token is needed. No X-Taal-Visitor header is
# sent, so no visitor state is created. These replace min-instances=1; pause them after judging
# (6 Nov 2026) with: ./infra/keepwarm.sh pause
#
# Requires: GOOGLE_CLOUD_PROJECT (amru-509214), REGION (asia-south1)
set -euo pipefail

: "${GOOGLE_CLOUD_PROJECT:?set GOOGLE_CLOUD_PROJECT}"
: "${REGION:?set REGION}"
AGENTS_URL="${AGENTS_URL:-https://taal-agents-2obkp776ca-el.a.run.app}"
WEB_URL="${WEB_URL:-https://taal-web-2obkp776ca-el.a.run.app}"
JOBS=(taal-agents-warm taal-web-keepwarm)

create_job() {  # name schedule uri
  gcloud scheduler jobs create http "$1" --project "$GOOGLE_CLOUD_PROJECT" --location "$REGION" \
    --schedule "$2" --time-zone UTC --uri "$3" --http-method GET \
    --attempt-deadline 30s --max-retry-attempts 0 \
    --description "Keep the service warm during judging; pause after 6 Nov 2026"
}

case "${1:-}" in
  create)
    create_job taal-agents-warm "*/5 * * * *" "$AGENTS_URL/health"
    create_job taal-web-keepwarm "*/10 * * * *" "$WEB_URL/"
    ;;
  pause|resume|delete)
    for j in "${JOBS[@]}"; do
      gcloud scheduler jobs "$1" "$j" --project "$GOOGLE_CLOUD_PROJECT" --location "$REGION" --quiet
    done
    ;;
  *) echo "usage: $0 create|pause|resume|delete" >&2; exit 2 ;;
esac
