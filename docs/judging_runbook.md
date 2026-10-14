# Judging runbook

For the judging window, 19 Oct to 6 Nov 2026. Live app: <https://taal-web-2obkp776ca-el.a.run.app>. API health: <https://taal-agents-2obkp776ca-el.a.run.app/health>. GCP project `amru-509214`, region `asia-south1`.

**Deploy rule: no deploy from 19 Oct to 6 Nov unless the live demo is broken.** A push to `main` deploys to Cloud Run (`.github/workflows/verify.yml`), so nothing merges in that window except a fix for a broken demo, and it is smoke-checked straight after.

**Who to call:** the owner, Nandish.

## Daily 5-minute smoke

Run it once a day from a checkout of `main` (needs only `python3`; no credentials):

```bash
make smoke-judging
```

`harness/smoke_judging.py` prints PASS or FAIL per check and exits non-zero if any fails. It uses one fresh `X-Taal-Visitor` sandbox per run, so the shared base tenant is never written. The chat turn must finish within 10 s and Approve within 5 s (`CHAT_MAX_S` and `APPROVE_MAX_S` in the script); a slower answer is a FAIL even when the content is right, because a judge waiting that long sees a broken demo. It makes two model calls (Plan live and one chat turn), so run it once, not in a loop.

| Check | Expected |
|---|---|
| Five web routes: `/`, `/desk`, `/phone`, `/chat`, `/outcomes` | HTTP 200 each |
| API `/health` | `status` ok; `model` set (currently `gemini-3.5-flash`, never the retiring `gemini-2.5-flash`); `plan_live_eval` present (22/24, p50 26.5 s, 11 Oct) |
| One Approve on Tea (`play_tea_ds04_v1`) | 355 treated, 39 held out; `copy.source` `existing`; `copy.provenance` `bigquery_pregenerated`; about 1.4 to 2.5 s warm; over 5 s FAILS |
| One chat turn as Ravi (`CUST-RAVI:web`) | a non-empty reply (one model call) in 10 s or less; slower FAILS |
| One Plan live (`POST /rerun` on `gap_tea_ds04`, then poll `/rerun/<run_id>`) | `status` done, `planner_source` model, about 20 to 35 s (one model call) |

Point it at other URLs with `make smoke-judging WEB=https://... API=https://...`. If a check fails, repeat that one step by hand once (an idle service can answer the first call slowly; a 503 `model_unavailable` clears after `retry_after_s`), then roll back below if it is still red.

## Rollback in 60 seconds

Cloud Run keeps every revision, so a bad deploy is undone by routing traffic back, not by redeploying. Do it per service; it takes effect in seconds. (This repeats `infra/README.md`, "Rollback in 60 seconds".)

```bash
# 1. list revisions, newest first; the one serving traffic is marked with a bullet
gcloud run revisions list --service taal-agents --region asia-south1 --project amru-509214
gcloud run revisions list --service taal-web    --region asia-south1 --project amru-509214

# 2. send 100% of traffic to the last good revision (copy its name from the list)
gcloud run services update-traffic taal-agents --to-revisions <rev>=100 --region asia-south1 --project amru-509214
gcloud run services update-traffic taal-web    --to-revisions <rev>=100 --region asia-south1 --project amru-509214

# 3. check
curl -s https://taal-agents-2obkp776ca-el.a.run.app/health
curl -s -o /dev/null -w '%{http_code}\n' https://taal-web-2obkp776ca-el.a.run.app/
make smoke-judging
```

`/health` must report `"status": "ok"` and the web root must answer 200. Roll back `taal-agents` and `taal-web` independently. After `update-traffic --to-revisions`, new deploys no longer take traffic automatically; return to the newest with `gcloud run services update-traffic <svc> --to-latest --region asia-south1 --project amru-509214` once a fix is deployed. Revisions serving on 14 Oct 2026: `taal-agents-00145-xvm` and `taal-web-00081-h95` (from `main` at 7b6ce15); the revisions before them were `taal-agents-00143-8v9` and `taal-web-00080-72v`.

## Spend caps and 429s

The model-calling endpoints are capped so an unauthenticated caller cannot run up the Gemini bill. Every cap is a 15-minute sliding window (900 s), kept in memory on the single `taal-agents` instance, so it resets on a redeploy or a cold start. Values are in `services/api/main.py` (`GLOBAL_PLAN_CAP`, `GLOBAL_CHAT_CAP`, `GLOBAL_CAPTURE_CAP` and the per-visitor numbers on each route).

| Endpoint | What it spends | Per visitor | Shared, all visitors |
|---|---|---|---|
| `POST /plan`, `POST /rerun` (Plan live) | one planner run (several model calls) | 20 | 120 |
| `POST /chat` | one chat turn | 60 | 600 |
| `POST /capture` with an uploaded photo | one vision read | 10 | 60 |

Sample photos (`photo_ref`), Approve, and every read endpoint are not capped. A "visitor" is the `X-Taal-Visitor` id the web app sends (or the client address without it).

What a 429 means for a judge: nothing is broken and nothing needs a deploy. The cap clears itself; the response carries a `Retry-After` header (whole seconds until the oldest counted call leaves the window, at least 1) and the demo works again after that. One judge is far from the per-visitor numbers; a shared cap is only reached by heavy traffic or abuse.

Telling the two apart by the message in `detail`:

- Per visitor: `rate limit: at most N <bucket> calls per 900s per visitor; wait and retry`. Only that browser is affected; another visitor id still works.
- Shared cap: `demo capacity: the shared limit of N <bucket> calls per 15 minutes is reached; try again in about S seconds`. Every visitor is affected for that bucket until calls age out.

Do not raise a cap during judging without the owner (a deploy is needed, and the rule above applies). To free a shared cap at once, restarting the instance clears the counters, which is also a deploy-level action.

Model Armor: off unless `TAAL_MODEL_ARMOR_TEMPLATE` is set on `taal-agents`; to switch it off without a code deploy: `gcloud run services update taal-agents --region asia-south1 --remove-env-vars TAAL_MODEL_ARMOR_TEMPLATE`. When on, a `/chat` envelope carries an optional `guard` object (prompt and reply verdicts); it fails open, so a Model Armor error lets the turn through.

## Keep-warm

`min-instances` stays 0 on `taal-agents` and `taal-web`. Two Cloud Scheduler jobs in `asia-south1` send a plain GET so a judge's first hit is usually warm:

| Job | Schedule | Request |
|---|---|---|
| `taal-agents-warm` | every 5 minutes | `GET /health` on the API (no model call, no BigQuery) |
| `taal-web-keepwarm` | every 10 minutes | `GET /` on the web app (a prerendered page, no API call) |

- Measured: after a 30-minute window with only the pings, the first real requests on 14 Oct (IST) took 0.34 s for the web root and 1.65 s for Approve; both services held one instance throughout. One round, with no cold baseline: `eval/raw/keepwarm_verification_2026-10-13.json`.
- It is not "always warm". If the demo has been idle the first load can take about 10 s (the README says so).
- Cost: about $0.10 a month for the fourth scheduler job in the project (two keep-warm plus two nightly jobs; the free tier is three per billing account).
- Commands: `./infra/keepwarm.sh create|pause|resume|delete` (needs `GOOGLE_CLOUD_PROJECT=amru-509214` and `REGION=asia-south1`). Pause both after judging, on 6 Nov: `./infra/keepwarm.sh pause`. Details: `infra/README.md`, "Keep-warm pings".
