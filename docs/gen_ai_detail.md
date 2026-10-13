# How Gen AI is used: full detail

Moved from the README on 14 Oct 2026, text unchanged except link paths. The README carries the current short version; dated figures below are as of the date they name.

## How Gen AI is used

Gemini 3.5 Flash on Vertex AI plans each play inside an ADK agent: it proposes the mechanic, audience and reasoning; plain code prices every rupee, runs eight guardrails, assigns the holdout and measures the lift. A proposal that fails a guardrail is sent back for a revision (up to 3 iterations) instead of being shown.

| Component | Model (id in `config/models.toml`) | What it decides | Deliberately not LLM |
|---|---|---|---|
| Vision intake | `flash` | SKU, best-before date, facings, confidence | which rows need confirmation; the sell-by date (rule) |
| Planner | `flash` in a LoopAgent | mechanic, audience, rationale, revision after a failed guardrail | every rupee (estimator), guardrails, holdout |
| Copy | `flash` via BigQuery `AI.GENERATE_TABLE` (vertex backend only). The 7 seeded plays carry BigQuery copy generated ahead of time (`fixtures/copy_pregenerated.json`, `make pregenerate-copy`) and Approve reuses it with no BigQuery call: `copy.source` `existing`, `copy.provenance` `bigquery_pregenerated`. A play without stored copy gets it from a background job started when it is proposed or opened, used if ready, else one call inside Approve under a 3 s budget (`copy.source` `bigquery`), else templated copy (`templated`). Before this change, on the live service on 13 Oct, `copy.source` read `bigquery` for the Tea hero (copy-ahead at startup, Approve 1.3 to 2.3 s) and `templated` for chips | vernacular variants for the seeded plays; BigQuery copy is not generated at click time for them | discount values, best-before disclosure (validator; runs on generated and templated copy alike) |
| Customer agent | `flash` | dialogue, substitution reasoning | stock, offer eligibility, arm, consent, order prices |
| Measure, Sense, Approve | none | | lift, CI, priors, assignment, forecast |

`TAAL_MODEL_BACKEND=stub` (the default, what CI runs) replaces Gemini with scripted models that follow the same tool protocol; `vertex` uses the pinned Gemini ids through Vertex AI (ids live only in `config/models.toml`).

**Recorded trace.** The 60-second beat opens on `gap_tea_ds04`: 103 units of Darjeeling Tea at dark store DS-04, ₹35,020 at stake, online sell-by 6 October 2026. Its Desk trace is a committed Gemini recording (`gemini-3.5-flash`, planner prompt v7), badged `Recorded from Gemini · 12 Oct 2026`: the pinned run `c/run_02` made one `propose_play` attempt, accepted first time with no rejection, in 26.8 s (`eval/raw/planner_real_traces_tea_2026-10-12c/`; pin in `eval/raw/seed_pins.json`). The play transfers the 103 units to OUT-01, nudges 394 consented customers and passes all eight guardrails. ₹9,191 is the estimator's recovered-versus-doing-nothing figure (waste avoided ₹9,397 minus transfer cost ₹206); the play still nets -₹25,829 against ₹35,020 at stake. ₹6,186 is derived, not a stored estimator field: the blanket 20% markdown's loss (₹32,015) minus the play's loss (₹25,829), a sum that `cite_or_drop` accepts when the final proposal's rationale states it (`agents/gate/guardrails.py`). Only that final rationale is checked: the earlier `check_guardrails` call in the trace ran on a draft with an empty rationale, so it cites no numbers. The second recorded gap, `gap_chips_ds07`, does not beat a blanket markdown (about ₹279 worse; the Desk shows both); its recording holds one schema slip, not a guardrail rejection. Details: [`docs/hero_plays.md`](hero_plays.md).

## What it does

**Capture** (pallet photo, confidence-scored, low rows confirmed) → **Sense** (nightly per-SKU forecasts, six gap types with rupees at stake) → **Plan** (ADK LlmAgent in a LoopAgent, max 3 iterations, six deterministic tools, eight guardrails) → **Approve** (holdout, best-before copy, offers for treated customers only) → **Engage** (Customer Agent grounded in stock, offers and consent; MCP orders; STOP withdraws consent) → **Measure** (treated vs holdout with a 95% CI; `unmeasured` when the treated arm is too small; priors updated).
