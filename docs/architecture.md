# Architecture

Services and data flow per DECISIONS §4. All request paths below are measured against the
latency budget in §4.3; none of the numbers here are pilot results (see `docs/pilot.md` for those).

## Services and data flow

```mermaid
flowchart LR
  subgraph Capture
    Phone[Phone view\ncamera + mic]
  end

  subgraph BigQuery[BigQuery: taal dataset]
    Sales[sales_daily / inventory_batches / inbound]
    Forecasts[forecasts / future_regressors]
    Gaps[gaps]
    Plays[plays / play_assignments]
    Outcomes[play_outcomes / estimator_priors]
  end

  subgraph AgentsSvc[taal-agents (Cloud Run, ADK)]
    Planner[Planner Agent]
    Approve[Approve + assignment]
    Customer[Customer Agent]
  end

  subgraph Web[taal-web (Cloud Run, Next.js)]
    PlayDesk[Play Desk]
    Chat[Customer web chat]
    Judge[Judge mode]
  end

  Firestore[(Firestore: stock / customers / offers / plays / substitutes)]

  Phone -- "1 photo/voice" --> AgentsSvc
  AgentsSvc -- "inventory_batches write" --> BigQuery
  Sales --> Forecasts --> Gaps
  Gaps -- "2 nightly Sense" --> Planner
  Planner -- "propose_play" --> Plays
  Plays -- "3 Approve" --> Approve
  Approve -- "assignment + re-forecast" --> Forecasts
  Approve -- "sync write" --> Firestore
  BigQuery -- "nightly mirror" --> Firestore
  Firestore -- "4 stock/offers" --> Customer
  Customer -- "orders" --> BigQuery
  BigQuery -- "5 nightly Measure" --> Outcomes
  Outcomes -- "Looker embed" --> PlayDesk
  PlayDesk --- Web
  Chat --- Web
  Judge --- Web
  AgentsSvc --- PlayDesk
  AgentsSvc --- Chat
```

## Request paths (numbered to match the video beats)

1. **Capture.** Phone view uploads a photo (or a spoken confirmation) to `taal-agents`; Vision
   intake writes confirmed rows to `taal.inventory_batches` with `source='photo'`.
2. **Sense → Plan.** The nightly `taal-sense` job (or an on-demand re-run) computes forecasts and
   gaps in BigQuery, then fans out gaps to the Planner Agent, which proposes plays.
3. **Approve.** A human (Play Desk or voice) approves a play; `taal-agents` writes
   `play_assignments`, inserts the play into `future_regressors`, and triggers a single-series
   `ML.FORECAST` re-run whose new p50 path the chart shows moving.
4. **Engage.** The Customer Agent reads `pending_offers` from Firestore on session start and
   delivers the play; a customer's order goes to `taal.orders` / `order_lines` with `play_id` set.
5. **Measure.** The nightly Measure job joins `orders` to `play_assignments` inside the play
   window, writes `play_outcomes` (treated vs holdout), and updates `estimator_priors`; Looker
   Studio reads the same table.

## Latency budget (DECISIONS §4.3)

| Path | Budget | Notes |
|---|---|---|
| Customer Agent turn | < 3 s p50 / < 6 s p95 | Flash, streaming; stock from Firestore; substitutes precomputed; no per-turn memory calls |
| Vision intake (one photo) | < 8 s | Gemini image understanding, strict output schema |
| Voice turn, first audio | < 2 s | Gemini Live API; recorded for the video regardless of live status at the finale |
| Planner, one gap | 20-60 s | nightly batch, or streamed on an on-demand re-run |
| Approve → re-forecast | < 15 s | single-series `ML.FORECAST` on a nightly pre-trained `ARIMA_PLUS_XREG` model; approve only updates `future_regressors` and re-runs `ML.FORECAST`, never retrains |
| Sense job (full nightly run) | minutes | never a live request path |

All figures in this table are **estimated** budgets from DECISIONS §4.3, not measurements; the
build replaces them with measured p50/p95 from Cloud Trace once services are deployed, and the
judge-mode footer's latency chips show the measured number for that run.

## What Gemini decides / what it is not allowed to decide

| Gemini decides | Gemini is not allowed to decide |
|---|---|
| Which mechanic fits a gap given prose policy, product context, festival calendar and past outcomes | Any rupee figure on a play, an offer or a dashboard -- every number is computed by the deterministic estimator (`agents/gate`) |
| How to revise a play when a guardrail fails, and when to escalate instead of looping forever | Whether a guardrail passes -- the gate functions are plain Python, unit-tested, and never consulted for a second opinion |
| The wording of vernacular copy for an approved play, inside constants passed in as "copy exactly" | The discount, price, or best-before date that appears in that copy -- those are constants; the validator query in `08_copy.sql` rejects a mismatch |
| What to say to a customer in chat, and which tool to call for stock, substitutes, or an order | Who is in the holdout arm, or whether an offer is sent to a holdout customer -- arm assignment is a deterministic hash (`FARM_FINGERPRINT`), checked again at delivery time |
| Which pallet-photo rows need a confirmation question versus which can be trusted | The forecast itself -- `AI.FORECAST` / `ARIMA_PLUS_XREG` are statistical models, not agent reasoning, and their output feeds gaps mechanically |

This is the one-line version from DECISIONS §2.7: "The rules decide what is allowed; Gemini
decides what to do; the estimator owns the numbers."
