# What is real, what is simulated: full detail

Moved from the README on 14 Oct 2026, text unchanged except link paths. The README carries the current short version; dated figures below are as of the date they name.

## What is real, what is simulated

Every panel carries a LIVE, REPLAY or SYNTHETIC badge; the Desk's trace names its source (`Recorded from Gemini · <date>`, `Scripted fixture`, `Rules (fallback)` or `Live · Gemini`). Approve, chat and capture are live calls; Sense is nightly and replayed. **Change policy → re-plan** is a live, streamed Gemini call on the deployed service. The judge-mode data is a frozen local snapshot per visitor; Reset restores it. BigQuery batch path status and the 27 Sep incidents: [eval/incidents_2026-09-27.md](../eval/incidents_2026-09-27.md).

| Part | Status | What it is, and the evidence |
|---|---|---|
| Forecasts, gaps, estimator, guardrails, planner loop | Real | Local forecaster (`jobs/sense/forecast.py`), gap detector, estimator, eight guardrails and the ADK planner run for real. |
| Approve, chat, orders, measurement code | Real | Assignment by hash, re-forecast, chat with Gemini, MCP orders, the lift and CI code. |
| Nightly BigQuery jobs | Real, not on the judge path | `AI.FORECAST` lost 45/45 head-to-head to the local forecaster, so the judge path uses the local one; `taal-sense` still runs it nightly (`eval/raw/bigquery_ai_forecast_2026-09-27/head_to_head_summary.json`). |
| Kutumb Mart tenant | Seeded | 300 grocery SKUs, 10 dark stores, 6 outlets, 4,000 customers, 70 days of sales (`eval/raw/docs_truth_sweep_2026-09-27/tenant_counts.json`). |
| Tea and chips plays | Seeded (recorded Gemini runs) | Committed recordings: Tea 12 Oct (pinned run `c/run_02`, `eval/raw/planner_real_traces_tea_2026-10-12c/`), chips 10 Oct (`eval/raw/planner_real_traces_2026-10-10/`). |
| Cola, kaju and quinoa plays | Seeded (scripted fixture) | From the scripted planner fixture (`infra/Dockerfile.api`). |
| Expected margin and write-off avoided after Approve | Projected | At the default response prior; a projection on a seeded tenant. |
| Outcomes screen | Synthetic | Labelled SYNTHETIC until a pilot runs (`docs/pilot.md`). |

Deployment caveat: `taal-agents` runs with `--max-instances 1` (`infra/deploy.sh:239`) because each visitor's sandbox is on the instance's local disk (`services/api/sandbox.py`) and re-plan run state is in process memory; a second instance would answer a poll with 404. `min-instances` is 0, so the first request after idle is slower.

## Scale, cost and pilot

- **Scale (estimate):** a Large profile (20,000 SKUs, 500 nodes, 1M customers) keeps the same shape; no tenant that size has run, so throughput is not measured. What breaks first is `--max-instances 1` (caveat above), then the Planner queue, then the in-process re-forecast ([`docs/scale.md`](scale.md)).
- **Run cost:** ₹486 a month measured on `gemini-2.5-flash` (usage to 23 Sep 2026, no plays in the window, not a bill; not re-measured on `gemini-3.5-flash`). Estimates: Micro ₹200 to 500, Mid ₹2,500 to 5,000, Large ₹1 to 2 lakh.
- **Pilot design:** 50 to 60 consented testers for one week, a 40 to 50% holdout, the metric pre-registered, results labelled apart from seeded numbers ([`docs/pilot.md`](pilot.md)). Nothing has been measured on real customers yet.

## Not in this submission

Voice (Gemini Live) is not part of this submission: it is a documented stub with no tests, and the phone view's microphone button is disabled.
