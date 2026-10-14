# Judging runbook

For the judging window, 19 Oct to 6 Nov 2026. Live app: <https://taal-web-2obkp776ca-el.a.run.app>. API health: <https://taal-agents-2obkp776ca-el.a.run.app/health>. GCP project `amru-509214`, region `asia-south1`.

**Deploy rule: no deploy from 19 Oct to 6 Nov unless the live demo is broken.** A push to `main` deploys to Cloud Run (`.github/workflows/verify.yml`), so nothing merges in that window except a fix for a broken demo, and it is smoke-checked straight after.

**Who to call:** the owner, Nandish.

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
