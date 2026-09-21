#!/usr/bin/env bash
# infra/smoke_test.sh -- an end-to-end smoke test against the live, deployed URLs, for
# `harness/checklists/infra_deploy.md`'s "infra/smoke_test.sh passes against the live URL".
#
# Unlike infra/smoke.sh (a /health-only check), this exercises four real things: /health on both
# services, a real gap read from Sense's output, a real /approve on an already-seeded play, and a
# real /chat reply from the live Gemini model -- all against a fresh, disposable
# X-Taal-Visitor sandbox overlay so nothing here ever mutates the base tenant or BigQuery.
#
# Usage: TAAL_AGENTS_URL=https://taal-agents-xyz.a.run.app \
#        TAAL_WEB_URL=https://taal-web-xyz.a.run.app \
#        ./infra/smoke_test.sh
#
# Requires: curl, python3 (stdlib json only).
set -euo pipefail

: "${TAAL_AGENTS_URL:?set TAAL_AGENTS_URL (the live taal-agents service URL)}"
: "${TAAL_WEB_URL:?set TAAL_WEB_URL (the live taal-web service URL)}"
PLAY_ID="${TAAL_SMOKE_PLAY_ID:-play_chips_ds07_v1}"
CUSTOMER_ID="${TAAL_SMOKE_CUSTOMER_ID:-CUST-MEENA}"
VISITOR="smoke$(date +%s)$$"
AGENTS="${TAAL_AGENTS_URL%/}"
WEB="${TAAL_WEB_URL%/}"

echo "== [1/4] health: taal-web ${WEB}/health =="
web_health="$(curl -sS -f --max-time 15 "${WEB}/health")"
echo "${web_health}" | grep -qi '"status"[[:space:]]*:[[:space:]]*"ok"' || { echo "FAIL: taal-web /health not ok: ${web_health}" >&2; exit 1; }
echo "OK: taal-web /health"

echo "== [1/4] health: taal-agents ${AGENTS}/health =="
agents_health="$(curl -sS -f --max-time 15 "${AGENTS}/health")"
echo "${agents_health}" | grep -qi '"status"[[:space:]]*:[[:space:]]*"ok"' || { echo "FAIL: taal-agents /health not ok: ${agents_health}" >&2; exit 1; }
echo "OK: taal-agents /health"

echo "== [2/4] a real gap: GET ${AGENTS}/gaps =="
gaps_body="$(curl -sS -f --max-time 15 "${AGENTS}/gaps")"
gap_id="$(echo "${gaps_body}" | python3 -c "import json,sys; d=json.load(sys.stdin); assert d, 'no gaps returned'; print(d[0]['gap_id'])")"
echo "OK: got a real gap: ${gap_id}"

echo "== [3/4] a real approve: POST ${AGENTS}/approve (play=${PLAY_ID}, visitor=${VISITOR} -- sandbox overlay, base tenant untouched) =="
approve_body="$(curl -sS -f --max-time 30 -X POST "${AGENTS}/approve" \
  -H "Content-Type: application/json" -H "X-Taal-Visitor: ${VISITOR}" \
  -d "{\"play_id\": \"${PLAY_ID}\"}")"
approve_status="$(echo "${approve_body}" | python3 -c "import json,sys; print(json.load(sys.stdin).get('status'))")"
if [ "${approve_status}" != "approved" ] && [ "${approve_status}" != "already_approved" ]; then
  echo "FAIL: /approve returned status=${approve_status}: ${approve_body}" >&2
  exit 1
fi
echo "OK: /approve -> status=${approve_status}"

echo "== [4/4] a real chat reply: POST ${AGENTS}/chat (customer=${CUSTOMER_ID}, visitor=${VISITOR}) =="
chat_body="$(curl -sS -f --max-time 30 -X POST "${AGENTS}/chat" \
  -H "Content-Type: application/json" -H "X-Taal-Visitor: ${VISITOR}" \
  -d "{\"session_id\": \"${VISITOR}:web\", \"text\": \"hi\", \"customer_id\": \"${CUSTOMER_ID}\"}")"
# /chat streams Server-Sent-Events ("data: {...}\n\n" lines); take the last non-empty data line.
chat_reply="$(echo "${chat_body}" | grep '^data: ' | tail -1 | sed 's/^data: //')"
reply_text="$(echo "${chat_reply}" | python3 -c "import json,sys; d=json.load(sys.stdin); t=d.get('text') or ''; assert t.strip(), 'empty text in chat reply'; print(t)")"
echo "OK: /chat replied: ${reply_text}"

echo "== smoke test passed (health x2, 1 real gap, 1 real approve, 1 real chat reply) =="
