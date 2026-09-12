# Taal

The agent that sells what the forecast says you'll throw away.

Retail & Commerce entry for the Google Cloud AI Builder Cup 2026 (JAPAC). Every forecast tells a
retailer what will be written off. Taal turns that into a play for the right customers, at the
right margin, approved by a human, entered into the forecast as a covariate, delivered by an
inventory-aware chat agent, and measured against a holdout.

## Judge quick-start

- Live URL: _pending deployment_ (`infra/deploy.sh`; the local demo runs with `make api` + `make web`, see Development).
- Click **Run the 60-second beat**, then **Approve**, and watch the forecast line move and the write-off change.
- Then **Chat as Meena**: the offer arrives in Kannada with the best-before date; ask for Cola Zero and get what is actually on her shelf.
- Video (under 3 min): _pending_ · Deck: _pending_
- Live vs replay: every panel carries a LIVE or REPLAY badge. Sense and Plan are nightly and replayed; approve, re-forecast, chat, capture and execution are live calls.
- Reset: **Reset demo data** restores the seeded tenant for your visitor only; nothing you do reaches anyone else.

## The hook

India's food regulator asks that food delivered online still has 30% of its shelf life or 45 days
left at delivery. Under the stricter reading a 90-day-shelf-life pack of chips that expires in
**51 days** can only be sold online for **6** more days. No forecasting tool knows that. Taal's
sell-by rule is a versioned tenant parameter (`config/tenant.demo.toml`, `sellby_rule`), shown on
every gap card; retailers set their own reading.

Demo gap `gap_chips_ds07`: 368 units of Masala Chips at dark store DS-07, ₹9,200 at stake, online
sell-by in 6 days. The planner's first draft (a 15% coupon) fails the margin floor; it revises to a
bundle; approval assigns 287 treated and 26 holdout customers by hash, writes the play into
`future_regressors`, re-forecasts the series in about 1.5 s, and Meena's chat delivers the offer.

## What it does

1. **Capture**: a node manager photographs a pallet; dates and counts are read with confidence scores; low-confidence rows must be confirmed before they reach inventory.
2. **Sense** (nightly): per-SKU, per-node forecasts with promo and festival regressors; five gap types (online sell-by breach, expiry write-off, stockout, rebalance, slow mover) with rupees at stake; segments; substitutes.
3. **Plan**: an ADK Planner Agent (LlmAgent inside a LoopAgent, max 3 iterations) designs a play with six deterministic tools; every number comes from the estimator; eight guardrails gate it; the Cost Governor decides which gaps are worth a model call.
4. **Approve**: assignment with a holdout, vernacular copy with the best-before line, offers for treated customers only, the play as a known future regressor, the chart moves.
5. **Engage**: a Customer Agent grounded in node stock, offers and consent; orders go through an MCP order endpoint; STOP withdraws consent.
6. **Measure**: treated vs holdout inside the play window, 95% CI, `unmeasured` when the treated arm is too small, priors updated by exact counts, a food-waste line in kg and CO2e labelled as an estimate.

## How Gen AI is used

| Component | Model (id in `config/models.toml`) | What it decides | Deliberately not LLM |
|---|---|---|---|
| Vision intake | `flash` | SKU, best-before date, facings, confidence | which rows need confirmation (threshold); the sell-by date (rule) |
| Planner | `flash` in a LoopAgent | mechanic, audience, rationale, alternatives, revision after a failed guardrail | every rupee (estimator), guardrails, holdout, play validity |
| Copy | `flash_lite` via BigQuery `AI.GENERATE_TABLE` | vernacular variants | discount values, best-before disclosure (validator) |
| Customer agent | `flash` | dialogue, substitution reasoning, envelope | stock, offer eligibility, arm, consent, order prices |
| Voice | `live` | intent, spoken summary | approve (explicit tool call after confirmation); stub in this build |
| Measure, Sense, Approve | none | | lift, CI, priors, assignment, forecast |

`TAAL_MODEL_BACKEND=stub` (the default and what CI runs) replaces Gemini with scripted models that
follow the same tool protocol, so the ADK agents, tools, session state, escalation and event log
are the real code paths and the decision policy is a script. `vertex` uses the pinned Gemini ids
through Vertex AI. Model ids live only in `config/models.toml`; verify each in Model Garden before the deploy.

## What is real, what is simulated

Real code paths: forecasts, gaps, estimator, guardrails, planner loop, assignment by hash,
re-forecast, chat, MCP orders, measurement. Simulated and disclosed: the tenant Kutumb Mart
(300 SKUs, 10 dark stores, 6 outlets, 4,000 customers, 70 days of sales) comes from a seeded
generator (`data/generator`) whose rule is stated in its docstring. No pilot has run yet; the
Outcomes screen is labelled SYNTHETIC until `docs/pilot.md` says otherwise. The local forecaster
stands in for BigQuery `AI.FORECAST` and `ARIMA_PLUS_XREG` (SQL under `data/bigquery/sense`).

## Development

```
make setup      # uv sync + npm ci (Playwright uses the pre-installed Chromium)
make verify     # secrets -> lint -> schemas -> generate -> unit -> sql -> agents -> api-test -> web-test -> docs -> status
make api        # FastAPI on :8080 against .local/data
make web        # Next.js on :3000 (NEXT_PUBLIC_TAAL_MOCK=1 for fixtures only)
make fixtures   # rebuild committed golden plays, mutations, golden runs, evalsets
make openapi    # regenerate docs/openapi.yaml
```

Green `make verify` is the only definition of done (`harness/`: builder and reviewer prompts,
per-component checklists, `STATUS.md`). Layout and specs: `docs/DECISIONS.md`; data model:
`docs/DATA_MODEL.md`; architecture: `docs/architecture.md`; scale and cost: `docs/scale.md`;
pilot design: `docs/pilot.md`; privacy: `docs/privacy.md`; API: `docs/openapi.yaml`.

## Licence

Apache-2.0 for code. Third-party data terms in `DATA_LICENSES.md`.
