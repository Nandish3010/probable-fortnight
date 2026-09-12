# Taal

The agent that sells what the forecast says you'll throw away.

Retail & Commerce entry for the Google Cloud AI Builder Cup 2026 (JAPAC). Every forecast tells a retailer what will be written off; Taal turns that into a play for the right customers, at the right margin, approved by a human, measured against a holdout.

## Judge quick-start

- Live URL: _pending deployment_
- Click **Run the 60-second beat**, then **Approve**, and watch the forecast move.
- Video (under 3 min): _pending_ · Deck: _pending_
- Live vs replay: panels are labelled LIVE or REPLAY; the nightly Sense and Plan stages are recorded, approve / chart / chat are live.
- Reset: the **Reset demo data** button restores the seeded tenant for your session only.

## What it does

1. **Capture**: a node manager photographs a pallet; best-before dates and counts are read and confirmed by voice.
2. **Sense**: per-SKU, per-node forecasts and gaps, including the online sell-by date required by India's food regulator (30% shelf life or 45 days remaining at delivery).
3. **Plan**: a planner agent designs a play (audience, mechanic, copy, expected outcome, guardrails, rationale) for a human to approve.
4. **Approve**: the play becomes a forecast covariate; the write-off number changes on screen; a holdout is assigned.
5. **Engage**: an inventory-aware chat agent delivers the offer and answers with the customer's local stock.
6. **Measure**: treated vs holdout; no lift is reported without a holdout.

## Architecture

_Diagram: `docs/architecture.png` (pending)._ BigQuery + BigQuery AI (AI.FORECAST, ARIMA_PLUS_XREG, VECTOR_SEARCH, AI.GENERATE_TABLE) · ADK agents on Cloud Run · Gemini on Vertex AI · Agent Platform Sessions and Simulation · Firestore · Cloud Storage · Looker Studio. Built with Antigravity and AI Studio.

## How Gen AI is used

| Component | Model | What it decides | Deliberately not LLM |
|---|---|---|---|
| Vision intake | Gemini Flash | dates, counts, confidence | which rows need confirmation (threshold) |
| Voice | Gemini Live | intent, spoken summary | approve (explicit tool call) |
| Planner | Gemini Flash | mechanic, audience, rationale, alternatives | every rupee (estimator), guardrails, holdout |
| Copy | Gemini Flash-Lite via BigQuery | vernacular variants | discount values, disclosure check |
| Customer agent | Gemini Flash | dialogue, substitution reasoning | stock, offer eligibility, consent |
| Measure | none | | lift, CI, priors |

## What is real, what is simulated

Real: agents, forecasts, guardrails, the pilot's orders and holdout. Simulated (seeded generator, disclosed): catalogue, sales history, stock and batches for the demo tenant Kutumb Mart. See `docs/DECISIONS.md` §3.

## Repository

See `docs/DECISIONS.md` for the full build guide: specs, schemas, tool contracts, evaluation, harness, cost model, team plan and submission checklist.

## Licence

Apache-2.0 for code. Third-party data terms in `DATA_LICENSES.md`.
