# Taal

The agent that sells what the forecast says you'll throw away.

Retail & Commerce entry for the Google Cloud AI Builder Cup 2026 (JAPAC). Every forecast tells a
retailer what will be written off. Taal turns that into a play for the right customers, at the
right margin, approved by a human, entered into the forecast as a covariate, delivered by an
inventory-aware chat agent, and measured against a holdout.

## Judge quick-start

- Live URL: https://taal-web-2obkp776ca-el.a.run.app (deployed via `infra/deploy.sh`; the local demo runs with `make api` + `make web`, see Development).
- Click **Run the 60-second beat**, then **Approve**, and watch the forecast line move and the write-off change.
- Then **Chat as Meena**: the offer arrives in Kannada with the best-before date; ask for Cola Zero and get what is actually on her shelf.
- Video (under 3 min): _pending_ · Deck: [`docs/deck.pdf`](docs/deck.pdf)
- Live vs replay: every panel carries a LIVE/REPLAY (or REAL PILOT/SYNTHETIC) badge -- the play card itself keeps its `REPLAY · policy <version>` badge -- except the Desk's trace panel and its re-plan result, which instead carry one of four provenance badges -- `Recorded from Gemini · <date>`, `Scripted fixture`, `Rules (fallback)`, or `Live · Gemini` -- naming exactly where that trace or run came from. Sense is nightly and replayed; approve, chat, capture and execution are live calls. **Change policy → re-plan** is itself a live, streamed call on the deployed service: it runs Gemini, streams each tool call and guardrail check as they happen, and ends badged with whichever of the four provenance kinds the run actually produced.
- Reset: **Reset demo data** restores the seeded tenant for your visitor only; nothing you do reaches anyone else.

## Screenshots

Captured with Playwright against the real local stack (`make api` + `make web`, mock mode off,
`TAAL_MODEL_BACKEND=stub`) -- real seeded data, not mocks. `web/tests/live/screens.spec.ts`
reproduces them.

No image in these screenshots, and none of the phone view's sample pallet photos
(`web/public/samples/pallet_0N.jpg`), is a real camera photo: all eight samples are AI-generated
renders (`fixtures/photos/README.md` says how that was determined). Vision accuracy on real phone
photos has not been measured yet.

| | |
|---|---|
| ![Judge mode landing page](docs/screenshots/judge-mode-landing.png) Judge mode landing | ![The 60-second beat's gap card, approve pending](docs/screenshots/60-second-beat-gap-card.png) 60-second beat: gap card |
| ![The 60-second beat after Approve, forecast chart moved](docs/screenshots/60-second-beat-approved-chart.png) 60-second beat: approved, chart moved | ![Play Desk with a play's guardrails, counterfactuals and trace](docs/screenshots/play-desk.png) Play Desk |
| ![Phone view intake table after a sample pallet photo capture](docs/screenshots/phone-view-intake-table.png) Phone view: intake table | ![Stylist chat with a real pairing reply and the sample-garment picker](docs/screenshots/stylist-chat-pairing.png) Stylist chat: pairing + garment picker |
| ![Outcomes screen with measured and unmeasured plays](docs/screenshots/outcomes-measured.png) Outcomes: measured | |

## The hook

India's food regulator asks that food delivered online still has 30% of its shelf life or 45 days
left at delivery. A 90-day-shelf-life pack of chips that expires in **33 days** can therefore
only be sold online for **6** more days. No forecasting tool knows that. Taal's sell-by rule is a
versioned tenant parameter (`config/tenant.demo.toml`, `sellby_rule`) shown on every gap card:
the default reads "either condition satisfies" (the earlier of the two cut-offs, which keeps bread
and milk sellable online); the stricter reading is one switch away and retailers set their own.

Demo gap `gap_chips_ds07`: 368 units of Masala Chips at dark store DS-07 (seeded), ₹9,200 at stake
(seeded), online sell-by in 6 days (computed) -- every number in this paragraph is recomputed by
`harness/flagship_facts.py` into `eval/raw/flagship_facts_2026-09-27.json`. The trace judges see for
this gap is the scripted stub planner, badged "Scripted fixture" -- **not** a Gemini run: its first
draft, a 15% coupon (seeded), fails the margin-floor guardrail; it revises to a bundle -- Masala
Chips with Coconut Water 1L, ₹61 for the pair (seeded). A real Gemini recording for this gap could
not be made in the build environment on 27 Sep 2026: no Google Cloud credential exists there.
`harness/record_flagship_traces.py` records one, and `make generate` seeds it automatically once a
recording is committed -- from that point on this gap's trace is badged `Recorded from Gemini ·
<date>` instead. Approval assigns 287 treated and 26 holdout customers by hash (seeded), writes the
play into `future_regressors`, and re-forecasts the series in about 2.0 s (measured locally against
the stub backend, not the deployed service); Meena's chat then delivers the offer. On the deployed
service, **Change policy → re-plan** instead runs Gemini live: the Desk streams each tool call and
guardrail check as it happens, and if no valid play arrives within the configured 45 s deadline
(configured) the deterministic-rules fallback runs instead, badged "Rules (fallback)" with the
reason shown.

## Why this generalizes: one decision loop, not a promo bot

The mechanism behind the hook is not specific to food. A `Play` (`docs/schemas/play.schema.json`)
is a single object -- target, mechanic, audience, guardrails, holdout, expected outcome -- and
`agents/gate/guardrails.py` and `agents/gate/estimator.py` never look at what kind of gap produced
it. The same loop runs today on two different problems with zero domain-specific code in the gate
layer:

- **Grocery**: `online_sellby_breach`, `expiry_writeoff`, `stockout_risk`, `rebalance`,
  `slow_mover` -- a forecast says a lot will go unsold before a deadline.
- **Apparel**: `unmet_demand` and `assortment_gap` -- customers ask the Stylist Agent for a style
  or colour the node does not stock; those real asks become a gap the same Planner, the same eight
  guardrails and the same holdout-measured Play loop can act on
  (`agents/stylist/tools.py`, `jobs/sense/gaps.py`).

Two more things close the loop rather than leaving it open-ended:

1. **Approve doesn't just log a decision, it feeds the forecast.** An approved play is written
   into `future_regressors` and the affected series is re-forecast immediately (the chart moving
   on screen in the 60-second beat *is* this) -- the agent's action becomes the model's next input,
   not a side effect the next Sense run has to catch up to.
2. **The estimator updates from evidence, not just once.** Every Measure run calls
   `update_prior()` (`agents/gate/estimator.py`, `jobs/measure/run.py`) and writes the new
   `alpha`/`beta` back to `estimator_priors`, keyed by mechanic, category and segment -- the next
   play of that shape starts from what was actually measured, not a static assumption.

## What Gemini decides / what it is never allowed to decide

Each row names the code that owns the decision and the test that fails if that boundary moves.
CI runs `TAAL_MODEL_BACKEND=stub` (scripted models, same tools and code paths), so the left-column
tests prove what the model's output must pass through, not how good the model is.

| Gemini decides | Code | Enforced by |
|---|---|---|
| Reading SKU, best-before date and count from a pallet photo, with a confidence per field | `agents/capture/vision.py:99` (`_vertex_rows`) | `tests/agents/test_vision.py:12`: rows validate against the schema; low-confidence rows are flagged |
| Proposing the play: shape, mechanic (and its parameters), audience segments, rationale; revising after a failed guardrail | `agents/planner/agent.py:101` (`LlmAgent` in a `LoopAgent`, max 3 iterations) | `tests/agents/test_planner.py:50`: the chips coupon fails the margin floor and the revision is a different, passing play |
| Offer copy wording, per segment and language (vertex backend only, at approve time; templated otherwise) | `jobs/sense/copy.py:95` (`AI.GENERATE_TABLE` at `:151`), gated by `validate_copy` at `:168` | `tests/unit/test_copy.py:39`: a variant stating the wrong best-before date is rejected |
| What to say to a customer, and which tool to call | `agents/customer/agent.py:38`, turn loop `agents/chat_runtime.py:160`, envelope clamped at `:180` | `tests/agents/test_customer.py:31` (every scripted conversation in `fixtures/conversations/`); `:88`: the exact on-hand count never reaches the customer |

| Never decided by Gemini | Code | Enforced by |
|---|---|---|
| Every rupee: expected units, margin, cost, counterfactuals | `agents/gate/estimator.py:216` (`estimate`); re-checked when a play is proposed, `agents/planner/tools.py:370` (`check_play_money`) | `tests/unit/test_estimator.py:32` (coupon arithmetic against a hand calculation); `tests/unit/test_invariants.py:45` (a play whose margin was altered after estimation is rejected) |
| Guardrail pass/fail: the eight rules | `agents/gate/guardrails.py:266` asserts the rule table equals `GUARDRAIL_RULES` in `agents/gate/models.py:42-45`; `check` at `:269` | `tests/unit/test_guardrails.py:28` (all eight run, in order); `:155` (consent_required ignores any model-written rationale) |
| Who is in the holdout: arm by hash of (customer, seed) | `services/api/approve.py:113` calls `agents/gate/assignment.py:23` (`assign_arm`, SHA-256 bucket) | `tests/unit/test_assignment.py:15` (arm is a pure function of seed and id); `:34` (model-written play fields cannot change an arm) |
| Consent: whether any offer may reach a customer; what STOP does | `agents/customer/tools.py:54` (`_consent_ok`), checked at `:104`, `:218`, `:260`; `record_stop` at `:354` withdraws consent and drops pending offers | `tests/agents/test_customer_gates.py:15`: after `record_stop`, context, `apply_offer` and `negotiate_offer` all refuse with no model turn |
| Forecast numbers, including the re-forecast on approve | `jobs/sense/forecast.py:127` (statistical model, no LLM); approve re-runs it at `services/api/approve.py:144` | `tests/sql/test_forecast.py:23`: an approved play changes p50 inside its window and nowhere else |
| Discount bounds: the category margin floor on every play; the ad-hoc chat discount ceiling | `agents/gate/guardrails.py:76` (`rule_margin_floor`); `agents/customer/tools.py:274` (`min(ad_hoc_max_discount_pct, margin headroom)`) | `tests/unit/test_guardrails.py:53`; `tests/unit/test_estimator.py:82` (property test: margin never below the floor when the gate passes); `tests/agents/test_customer_gates.py:36` (every catalogue sku) |

Two limits, stated rather than hidden. **STOP recognition is the model's call.** The prompt tells
the Customer Agent to call `record_stop` on "STOP" (`agents/customer/prompts/customer.md:38`), and
only the scripted conversations 10-12 cover that step. What STOP does after the call, and every
consent check after it, is code. **The copy validator checks the percentage and the best-before
date, not rupee amounts** in the text (`jobs/sense/copy.py:168`); a bundle price the model misstates
in words would pass it.

## How this differs, by product category

What each category does on the three things this build is designed around. A named product would
appear in a row only with a fetched public documentation page behind each cell. None does: on
2026-09-27 every vendor documentation site tried was refused by this build environment's network
policy, so nothing about any named product could be checked, and no cell here says what any vendor
does or does not do. The Taal row cites code and tests; the category rows are open until a page is
fetched and cited.

| | Treats the online sell-by cut-off as the deadline | Holdout on every play by default | An approved action is fed back into the forecast |
|---|---|---|---|
| **Taal** | Yes: each lot's `online_sellby_date` comes from the tenant's versioned rule (`agents/gate/sellby.py:24`), and a dark-store lot's deadline is that date, not expiry (`jobs/sense/gaps.py`, `deadline = sellby if ...`); `tests/unit/test_sellby.py`, `tests/unit/test_ingest.py` | Yes: `holdout_required` is one of the eight rules every play must pass (`agents/gate/guardrails.py:157`); tenant floor `min_holdout_fraction = 0.05`; `tests/unit/test_guardrails.py:98` | Yes: approve writes the play into `future_regressors` and re-forecasts the series (`services/api/approve.py:144`); `tests/sql/test_forecast.py:23` |
| Markdown-optimisation tools | not verified: public documentation checked on 2026-09-27 could not be fetched | not verified: public documentation checked on 2026-09-27 could not be fetched | not verified: public documentation checked on 2026-09-27 could not be fetched |
| Demand-planning suites | not verified: public documentation checked on 2026-09-27 could not be fetched | not verified: public documentation checked on 2026-09-27 could not be fetched | not verified: public documentation checked on 2026-09-27 could not be fetched |
| CX / marketing agents | not verified: public documentation checked on 2026-09-27 could not be fetched | not verified: public documentation checked on 2026-09-27 could not be fetched | not verified: public documentation checked on 2026-09-27 could not be fetched |

## What it does

1. **Capture**: a node manager photographs a pallet; dates and counts are read with confidence scores; low-confidence rows must be confirmed before they reach inventory.
2. **Sense** (nightly): per-SKU, per-node forecasts with promo and festival regressors; seven gap types across two domains -- grocery write-off risk (online sell-by breach, expiry write-off, stockout, rebalance, slow mover) and apparel demand signal (unmet demand, assortment gap) -- with rupees at stake; segments; substitutes.
3. **Plan**: an ADK Planner Agent (LlmAgent inside a LoopAgent, max 3 iterations) designs a play with six deterministic tools; every number comes from the estimator; eight guardrails gate it; the Cost Governor decides which gaps are worth a model call.
4. **Approve**: assignment with a holdout, vernacular copy with the best-before line, offers for treated customers only, the play as a known future regressor, the chart moves.
5. **Engage**: a Customer Agent grounded in node stock, offers and consent; orders go through an MCP order endpoint; STOP withdraws consent.
6. **Measure**: treated vs holdout inside the play window, 95% CI, `unmeasured` when the treated arm is too small, estimator priors updated from the exact treated/responder counts so the next play of that shape starts from real evidence, a food-waste line in kg and CO2e labelled as an estimate.

## How Gen AI is used

| Component | Model (id in `config/models.toml`) | What it decides | Deliberately not LLM |
|---|---|---|---|
| Vision intake | `flash` | SKU, best-before date, facings, confidence | which rows need confirmation (threshold); the sell-by date (rule) |
| Planner | `flash` in a LoopAgent | mechanic, audience, rationale, alternatives, revision after a failed guardrail | every rupee (estimator), guardrails, holdout, play validity |
| Copy | `flash` via BigQuery `AI.GENERATE_TABLE` (vertex backend only, at approve time; falls back to templates on any failure/timeout) | vernacular variants | discount values, best-before disclosure (validator; runs on generated and templated copy alike) |
| Customer agent | `flash` | dialogue, substitution reasoning, envelope | stock, offer eligibility, arm, consent, order prices |
| Stylist agent | `flash` (+ vision) | dialogue, which pairing to lead with, reading a garment or selfie photo into attributes | colour theory (hue wheel), stock at the node, the demand-signal write, trend aggregation, colour family and skin-tone confirmation, checkout, and the assortment_gap this demand signal raises when it resolves to real supply elsewhere -- same guardrail-gated, holdout-measured play loop as the grocery gaps |
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
Outcomes screen is labelled SYNTHETIC until `docs/pilot.md` says otherwise.

**Forecasting and the nightly batch split, stated once here** (the same wording appears in
`docs/architecture.md`, `docs/scale.md`, `infra/README.md`): the judge-mode serving path
(`taal-agents`, this app) always reads a frozen, pinned-clock local snapshot and never touches
BigQuery directly -- what a judge clicks never depends on a nightly job having run. Behind that,
`jobs/sense` and `jobs/measure` support two backends, selected by env vars that default to the
local path everywhere except the `taal-sense`/`taal-measure` Cloud Run Jobs' own environment:
`TAAL_FORECAST_BACKEND=local` (the pure-Python forecaster) or `bigquery_timesfm`, which runs
BigQuery `AI.FORECAST` (TimesFM) for real; `TAAL_BATCH_STORE=local` (JSONL) or `bigquery`, which
writes through `agents/gate/bigquery_store.py::BigQueryStore`. `AI.FORECAST` was verified live
against project `amru-509214` in `asia-south1`: available, no covariate/regressor parameter
(confirmed by a real rejection), a real SQL bug found and fixed, and a full run across all 895
qualifying series (25,060 rows, ~23s, ~70MB billed) -- evidence in
`eval/raw/bigquery_ai_forecast_2026-09-27/`. A head-to-head backtest against the local model, same
rolling origins as `jobs/sense/backtest.py`, found the local model with lower MAPE in every one of
45 (origin, tier) comparisons -- expected, since the seeded data was generated with the same form
the local model fits; see `head_to_head_summary.json` in that directory. **A billing/payment issue
on the GCP project briefly blocked all BigQuery writes on 2026-09-27** (DML, streaming inserts and
load jobs all failed with `billingNotEnabled` for roughly the 15:31-15:33 UTC window and after);
this has since been resolved by the project owner and re-verified live, twice, over an hour apart
(streaming insert, DML `INSERT`/`DELETE`, `LOAD`, `CREATE TABLE` and `DROP TABLE` all succeeding
cleanly). No data was lost during the outage. **A separate, real data-loss bug was found and fixed
the same day** (before it ever ran against a project with billing enabled): `BigQueryStore.write()`
used a tenant-wide `DELETE` even on `forecasts`, a history table, which would have wiped every
prior run's rows on the very next nightly write; `run.py` also unconditionally re-wrote `forecasts`
through that path even when the `bigquery_timesfm` backend had already persisted the same rows via
real SQL `INSERT`s. Fixed: `run.py` no longer re-writes `forecasts` for the `bigquery_timesfm`
backend; `BigQueryStore.write()` now scopes `forecasts` deletes to `(tenant_id, run_id)` (never
tenant-wide), stages new rows in a throwaway table and swaps them in via a single `BEGIN
TRANSACTION`/`COMMIT TRANSACTION` script, so a failed load or swap always leaves the existing rows
untouched; date/Decimal values are made JSON-safe before any load. `load_table_from_json` with
`WRITE_TRUNCATE` into an existing table was also found to silently reorder and drop nested
`STRUCT` subfields when no explicit schema is passed -- fixed by always passing the real, fetched
target schema. Evidence, tests and the full bug chain: `eval/raw/bigquery_forecast_dataloss_2026-09-27/`,
`tests/unit/test_bigquery_store.py`, `tests/unit/test_sense_bigquery_backend.py`.

**The `taal.gaps` DDL/code mismatch this uncovered has been migrated live and re-verified**:
`evidence` was missing not just `counterpart_gap_id` (rebalance gaps) but 14 more fields
`jobs/sense/gaps.py` has always emitted for online_sellby_breach/expiry_writeoff, stockout_risk,
slow_mover, unmet_demand and assortment_gap gaps -- roughly 80% of all gaps by volume. All 15
fields are now live on `taal.gaps` (additive, nullable; no field dropped, renamed or retyped), and
`infra/deploy.sh` gained a permanent, idempotent migration step so a fresh deploy never falls
behind the DDL again. **The nightly BigQuery batch path (`TAAL_BATCH_STORE=bigquery`,
`TAAL_FORECAST_BACKEND=bigquery_timesfm`) is now verified against a staging clone of `taal`**: a
full `jobs.sense` run against `taal_staging` succeeded end-to-end (533 gaps across all 6 real gap
types, all 7 rebalance gaps carrying `counterpart_gap_id`, prior forecast runs untouched). It has
not yet been run for real against `taal` itself -- see
`eval/raw/bigquery_schema_migration_2026-09-27/finding.json` for the full migration record and
`eval/raw/bigquery_billing_dml_2026-09-27/finding.json` for the billing timeline. The
stylist's apparel catalogue (~350 SKUs across ~45 garment types, sized stock at dark stores) comes
from the same seeded generator on its own RNG stream. So does its demand: `~485` `style_requests`
across the same 70-day window and 4,000-customer base as the grocery side, on a third RNG stream,
by a stated rule (`data/generator/apparel.py::generate_style_requests`) -- tier-weighted asking
frequency, one "hot" dark store per cluster, a couple of trending (garment, colour) pairs per
cluster so real trends emerge from aggregation, and a festival-window lift on festive/wedding
occasions from the same calendar the grocery side uses. `jobs/sense/trends.py` aggregates these
into `style_trends`, and `jobs/sense/gaps.py` resolves unfulfilled clusters of them into
`assortment_gap` rows the same way `rebalance` gaps work for grocery. None of this is a forecast or
hand-placed to hit a target count; the trends and assortment-gap panels are labelled SYNTHETIC the
same way the Outcomes screen is. Garment and selfie photo fixtures remain generated colour
swatches, never real photos -- turning them into real, self-shot photographs needs a physical
camera and staged garments this build does not have; see `docs/DECISIONS.md` §5.9 for that gap.

## Related work

Two outside references anchor design decisions here, rather than left as unverified intuition:

- **[OTTO's forecasting team, "Team Lumen"](https://cloud.google.com/customers/otto)** put a
  Time-series Dense Encoder (TiDE) model on Vertex AI, BigQuery and GKE and measured up to a 30%
  improvement in demand-forecast accuracy for seasonal inventory. It is the production evidence
  that this project's own choice of stack (BigQuery `AI.FORECAST`/`ARIMA_PLUS_XREG` on Vertex) is
  not a hackathon-only convenience -- the same primitives already carry real retail forecasting
  load elsewhere.
- **Winkelmann, Elbracht, Brenker & Gerzen, ["Discounted Sales of Expiring Perishables: Challenges
  for Demand Forecasting in Grocery Retail Practice"](https://arxiv.org/abs/2602.04464)** (Feb
  2026), a two-step regression study over 1,700+ SKUs across 676 stores of a major European
  grocery retailer, finds that standard demand forecasts systematically underestimate the demand
  uplift a markdown produces on expiring stock -- because the discount itself is not fed back into
  the forecast as a covariate. That is precisely the gap Taal's approve step closes: an approved
  play is written into `future_regressors` and the series is re-forecast with the play as a known
  covariate, rather than left for the next forecast cycle to be surprised by the uplift after the
  fact.

## Related work: AP2 vocabulary for consent and approval

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

## Bring your own data

- **Three files**: `products.csv`, `inventory_batches.csv`, `sales.csv` (columns in [`docs/scale.md`](docs/scale.md#the-three-csv-ingestion-contract); worked example in [`data/samples/`](data/samples/)); `nodes.csv` and `inbound.csv` are optional.
- **One command**: `uv run python -m data.ingest --products products.csv --batches inventory_batches.csv --sales sales.csv --tenant config/tenant.<name>.toml --out .local/data-<name>` (copy `config/tenant.demo.toml` to set your sell-by rule, margin floors and thresholds).
- **What you get back**: every lot flagged under your online sell-by rule, units and rupees at stake by gap type, the ten largest gaps, and the stock already past its online sell-by or expiry; errors name the file, line and column.
- **Nothing leaves the machine**: ingest pins the store and forecaster to local files and switches off the serving cache, whatever your environment says.
- **A pilot is one command from here**: `TAAL_DATA_DIR=.local/data-<name> TAAL_TENANT_CONFIG=config/tenant.<name>.toml make api` serves those gaps over the same API the Play Desk reads (`eval/raw/ingest_roundtrip_2026-09-27/api_probe.txt`). Planning a play returns `no_play` until customer and consent tables exist, because the three files carry no audience; that is the pilot's first step ([`docs/pilot.md`](docs/pilot.md)).

## Evaluation

[`eval/evaluation_table.md`](eval/evaluation_table.md) is the DECISIONS §12 submission table,
built by `make eval-table` from `eval/evaluation.md` and `eval/raw/` -- every cell is parsed from
already-committed, already-measured output, never typed by hand. `eval/evaluation.md` is the dated
narrative behind it: every number names the command that produced it and links to the raw output
committed under `eval/raw/`. Rows §12 asks for that this project genuinely cannot produce yet
(pilot results, Gemini-as-judge scoring, cost from a billing export, planner throughput timing) say
so explicitly in the table rather than a guessed number.

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

## Trying it in GitHub Codespaces

Open the repo on GitHub, Code → Codespaces → Create. The devcontainer installs everything and runs
`make generate`. Then, in two terminals:

```
make api
NEXT_PUBLIC_TAAL_API_URL=https://<your codespace name>-8080.app.github.dev make web
```

Port 8080 is forwarded as public by the devcontainer so the browser can reach the API; port 3000
opens automatically. Stop the Codespace when you are done.
