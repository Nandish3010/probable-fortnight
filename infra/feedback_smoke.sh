#!/usr/bin/env bash
# infra/feedback_smoke.sh -- after a deploy, prove the live practitioner feedback path end to end:
# the API writes to Firestore (not the container disk), the deployed web origin passes CORS, a
# submission is accepted, and -- when the admin token is readable -- that same submission can be
# found and deleted again by a separate request. Run by infra/deploy.sh; exits non-zero on failure,
# which fails the deploy job.
#
# The probe is marked source=test, so it is excluded from every analysis even if it cannot be
# deleted; it never counts as a response.
#
# Usage: TAAL_AGENTS_URL=https://... TAAL_WEB_ORIGIN=https://... GOOGLE_CLOUD_PROJECT=... \
#        bash infra/feedback_smoke.sh
set -euo pipefail

: "${TAAL_AGENTS_URL:?set TAAL_AGENTS_URL}"
: "${TAAL_WEB_ORIGIN:?set TAAL_WEB_ORIGIN (the deployed taal-web origin)}"
API="${TAAL_AGENTS_URL%/}"

field() { python3 -c "import json,sys; print(json.load(sys.stdin).get('$1', ''))"; }

echo "== feedback store =="
store="$(curl -sS -f --max-time 60 --retry 3 --retry-all-errors "${API}/health" | field feedback_store)"
echo "   feedback_store=${store}"
expected="${EXPECT_FEEDBACK_STORE:-firestore}"  # override only to exercise this script against a local API
[ "${store}" = "${expected}" ] || { echo "FAIL: feedback would be written to '${store}', not ${expected}" >&2; exit 1; }

echo "== CORS preflight from ${TAAL_WEB_ORIGIN} =="
allowed="$(curl -sS -o /dev/null -D - --max-time 30 -X OPTIONS "${API}/feedback" \
  -H "Origin: ${TAAL_WEB_ORIGIN}" -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: content-type,x-taal-visitor" \
  | tr -d '\r' | awk -F': ' 'tolower($1)=="access-control-allow-origin"{print $2}')"
[ "${allowed}" = "${TAAL_WEB_ORIGIN}" ] || { echo "FAIL: the browser form would be blocked by CORS (allow-origin='${allowed}')" >&2; exit 1; }
echo "   ok"

echo "== submit a source=test probe =="
version="$(curl -sS -f --max-time 30 "${API}/feedback/form" | field form_version)"
body="{\"form_version\":\"${version}\",\"mode\":\"interview\",\"source\":\"test\",\"answers\":{\"a1_role\":\"other\",\"a1_role_other\":\"deploy smoke probe\",\"a2_business\":\"other\",\"e4_consent\":true}}"
rid="$(curl -sS -f --max-time 30 -X POST "${API}/feedback" -H "Origin: ${TAAL_WEB_ORIGIN}" \
  -H "Content-Type: application/json" -H "X-Taal-Visitor: deploy-smoke" -d "${body}" | field response_id)"
[ -n "${rid}" ] || { echo "FAIL: no response_id returned" >&2; exit 1; }
echo "   stored as ${rid}"

echo "== read it back by deleting it (needs the admin token) =="
token="${TAAL_FEEDBACK_ADMIN_TOKEN:-}"
[ -n "${token}" ] || token="$(gcloud secrets versions access latest --secret taal-feedback-admin-token --project "${GOOGLE_CLOUD_PROJECT:-}" 2>/dev/null || true)"
if [ -z "${token}" ]; then
  echo "   WARNING: admin token not readable here; the probe stays in Firestore as source=test (excluded from analysis)"
  exit 0
fi
code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 30 -X DELETE "${API}/feedback/${rid}" -H "Authorization: Bearer ${token}")"
[ "${code}" = "200" ] || { echo "FAIL: DELETE of the probe returned ${code}; the submission was not found in the store" >&2; exit 1; }
echo "OK: feedback is stored in Firestore and deletable by response_id"
