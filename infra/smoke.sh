#!/usr/bin/env bash
# infra/smoke.sh -- curl /health of the live URL(s) and fail on a non-ok response. Intended for
# a weekly GitHub Action (DECISIONS §17.2 "a weekly live-URL smoke test through 4 Dec").
#
# Usage: TAAL_AGENTS_URL=https://taal-agents-xyz-uc.a.run.app \
#        TAAL_WEB_URL=https://taal-web-xyz-uc.a.run.app \
#        ./infra/smoke.sh
set -euo pipefail

: "${TAAL_AGENTS_URL:?set TAAL_AGENTS_URL (the live taal-agents service URL)}"
: "${TAAL_WEB_URL:?set TAAL_WEB_URL (the live taal-web service URL)}"

check() {
  local name="$1" url="$2"
  echo "== checking ${name}: ${url}/health =="
  body="$(curl -sS -f --max-time 15 "${url}/health")" || {
    echo "FAIL: ${name} did not respond" >&2
    exit 1
  }
  echo "${body}"
  if ! echo "${body}" | grep -qi '"status"[[:space:]]*:[[:space:]]*"ok"'; then
    echo "FAIL: ${name} /health did not report status ok" >&2
    exit 1
  fi
  echo "OK: ${name}"
}

check taal-agents "${TAAL_AGENTS_URL}"
check taal-web "${TAAL_WEB_URL}"

echo "== smoke test passed =="
