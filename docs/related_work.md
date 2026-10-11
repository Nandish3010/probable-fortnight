# Related work

Moved from the README. Two outside references anchor design decisions, then the AP2 vocabulary for consent and approval.

## Forecasting references

- **[OTTO's forecasting team, "Team Lumen"](https://cloud.google.com/customers/otto)**, as reported
  in Google Cloud's customer story: a Time-series Dense Encoder (TiDE) model, trained on Vertex AI
  and deployed on GKE, drawing on BigQuery as a data source, which the story credits with up to a
  30% improvement in demand-forecast accuracy; the story's own worked example is seasonal
  inventory (gaming consoles). Taal's own forecaster is different: the local seasonal-xreg
  forecaster (`jobs/sense/forecast.py`). We benchmarked BigQuery `AI.FORECAST` (TimesFM) against the local seasonal model on 45 backtest comparisons (5 origins x 9 category tiers); the local model won 45/45, so the judge-facing path uses the local forecaster; the nightly `taal-sense` job still runs `AI.FORECAST` (`infra/deploy.sh:309`) and its output is not read by the judge-facing path (see
  [eval/incidents_2026-09-27.md](../eval/incidents_2026-09-27.md)).
- **Winkelmann, Elbracht, Brenker & Gerzen, ["Discounted Sales of Expiring Perishables: Challenges
  for Demand Forecasting in Grocery Retail Practice"](https://arxiv.org/abs/2602.04464)** (Feb
  2026) -- its title names a real, open problem: forecasting demand for discounted, soon-to-expire
  perishables in grocery retail. Taal's own design takes a stance on one piece of that problem: an
  approved play is written into `future_regressors` and the series is re-forecast with the play's
  promo flag as a known covariate, rather than left for the next forecast cycle to be surprised by
  the uplift after the fact.

## AP2 vocabulary for consent and approval

Google's [Agent Payments Protocol (AP2)](https://cloud.google.com/blog/products/ai-machine-learning/announcing-agents-to-payments-ap2-protocol)
names three stages of machine-to-machine consent as signed Mandates: **Intent** (what the user
authorised an agent to do, and its scope), **Cart** (the exact items and price the user approved),
and **Payment** (authorisation to charge a specific instrument). Taal does not implement AP2's
protocol or its cryptographic Verifiable Credentials -- there is no agent-to-agent payment here,
only one retailer's own agent talking to its own customer -- but the same three-stage discipline
already existed in this codebase before AP2 was named, and stating it in AP2's vocabulary makes the
design legible to anyone who already knows that framework:

| AP2 concept | Taal's equivalent |
|---|---|
| Intent Mandate | Marketing consent (`consent` table) plus the guardrail-approved play itself: what this customer may be offered, and under what limits (frequency cap, margin floor) |
| Cart Mandate | `apply_offer(play_id, customer_id)` -- the customer's own `add:<sku>` click locks in the exact play, sku and discount before `place_order` runs |
| Payment Mandate | `place_order(...)` -- the MCP order tool executes the transaction against the cart `apply_offer` already fixed |

"STOP" (`record_stop`) revokes the Intent Mandate outright: the consent gate re-checks it on every
proposed play, not just at signup.
