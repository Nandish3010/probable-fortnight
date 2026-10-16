# Taal

Taal turns a write-off forecast into a human-approved play (a transfer, an offer or both). The agent is refused by code until it designs a control group, and it tells you when the result has not proved anything yet.

For a dark-store team clearing a lot before its online sell-by: on the live Desk, 103 packs of Darjeeling Tea, 24 days left, ₹35,020 at stake. Forecast, Propose, Approve, Offer, Measure. Retail & Commerce, AI Builder Cup 2026.

**What is new here**
- **The agent is refused until it designs its own control group.** `rule_holdout_required` rejects any play without a valid holdout fraction, minimum treated count and seed (`agents/gate/guardrails.py:161-173`).
- **It says when nothing is proved yet.** A holdout interval that crosses zero reads INCONCLUSIVE, labelled SYNTHETIC, and the power simulation states the data a real answer needs: about 1,156 customers for a 5 pp lift (`eval/raw/holdout_power_2026-10-14.json`). The ₹9,191 stays labelled PROJECTED.
- **Each safety layer measured on its own.** The tool refuses another customer's id in every run although the chat model tries it 3 of 3 times (`agents/customer/tools.py:43-59`); Model Armor blocks 3 of 8 chat injection cases and fails open (`eval/evaluation.md:1167-1172`).
- **A pre-registered, frozen eval.** The protocol was committed before any model call; a run is INVALID if a fallback model answers; the harness enforces a spend cap (`eval/adversarial/PROTOCOL.md`).
- **Cite-or-drop that resists tricks.** Rationale numbers must match the play in Western or Indian digit grouping (`agents/gate/guardrails.py:221-228`); copied untrusted phrases are caught after folding look-alike and invisible characters (`agents/gate/untrusted.py:18-38`).

**Why us.** We are in a category team at Supertails, an Indian pet-care e-commerce company: Nandish on pricing, Rinu on online sales and part of the P&L. Near-expiry and slow-moving stock is a standing cost: written off, or holding storage and capital. Phase 1 is near-expiry stock; phase 2, slow-moving SKUs. Taal has not been used at Supertails; all data is synthetic.

| Result | Figure | Label |
|---|---|---|
| Hero play vs doing nothing | Transfer to the outlet that can sell the tea plus a targeted nudge: **₹9,191** projected recovery (₹9,397 waste avoided minus ₹206 transfer cost) | PROJECTED, synthetic |
| Beat a blanket 20% markdown | **₹6,186** | PROJECTED, derived |
| Holdout | 355 treated, 39 held out; lift +0.3 pp, 95% CI -8.7 to +1.6. A 5 pp lift needs about 1,156 customers (SIMULATION) | inconclusive, synthetic |
| Adversarial eval | 50 of 60 attack runs stopped, 0 of 18 genuine requests refused (20 attacks, 6 controls, 3 runs each). 10 of 60 runs (4 cases) got through; all 4 cases fixed in code since and re-run (the model still attempts the consent change; the tool refuses it). [Details](eval/evaluation.md#v6-fix-re-run-16-oct-2026-code-only-the-frozen-results-above-are-unchanged) | MEASURED, `gemini-3.5-flash`, 14 Oct; V6 re-run 16 Oct |
| Model Armor | Screens every chat message and reply; verified live; fails open (the turn goes ahead, marked, and code guardrails still apply) | MEASURED, `taal-agents-00149-sw6`, 14 Oct |
| Live Plan | 22/24 Gemini-authored, p50 26.5 s, p95 31.8 s | MEASURED, `gemini-3.5-flash`, prompt v6, 11 Oct (v7 ships; not re-run) |
| Planner evalsets | First proposal accepted 39/46; response match 46/46; strict trajectory 18/46 against same-model recordings (a regression guard, not accuracy) | MEASURED, `gemini-3.5-flash`, prompt v7, re-recorded 14 Oct |
| Approve | 1.4 to 1.9 s warm (10 samples) | MEASURED, 13 to 15 Oct, `taal-agents-00155-drd` |
| Chat latency (Model Armor on) | p50 3.66 s, p95 4.36 s (p95 was 8.44 s) | MEASURED, `gemini-3.5-flash`, 14 Oct, local API |
| Accessibility | 0 serious or critical axe issues | MEASURED, mock mode, 14 Oct |
| Tests | 870 pytest, 833 Playwright (+34 live) | collected, 16 Oct; `make verify` gate |

Sources: [`eval/raw/`](eval/raw/), [`deck/claims.md`](deck/claims.md).

## Judge quick-start

No sign-in; each visitor gets a private sandbox. Synthetic data, demo clock 12 Sep 2026; after idle, first load takes about 10 s. Model calls have [fair-use limits](#impact-and-limits).

1. Open <https://taal-web-2obkp776ca-el.a.run.app> and click **Run the 60-second beat**. You land on the Darjeeling Tea gap.
2. Click **Approve**: it reads "Recovered vs doing nothing ₹9,191" (projected): 355 customers treated, 39 held out.
3. Click **Chat as Ravi**. It asks "Any offers today?" for him and the Tea offer arrives. Click **Add to cart**: the order total is ₹450.

Then type (checked live, 15 Oct):

| You type | Expected reply |
|---|---|
| Is the Darjeeling tea in stock? | Yes: 100g and 250g packs, with Add to cart |
| Do you have Cola Zero? | Yes: the sizes in stock (synthetic prices) |
| STOP | Unsubscribed; pending offers dropped |

Also try **Plan live** (a live Gemini re-plan, about 27 s).

| Live app | Video | Deck | Repo | API health |
|---|---|---|---|---|
| [taal-web](https://taal-web-2obkp776ca-el.a.run.app) | [Demo video (2:35)](https://drive.google.com/file/d/1hBKapntHMnc4FNybRqSEWods2MTrluBw/view?usp=sharing) | [PDF](docs/deck.pdf) | [GitHub](https://github.com/Nandish3010/probable-fortnight) | [/health](https://taal-agents-2obkp776ca-el.a.run.app/health) |

## How Gen AI is used

`gemini-3.5-flash` on Vertex AI does the language and judgement work; `gemini-3.5-flash-lite` is the fallback on 404, 429 or 5xx.

- **Planner.** An ADK `LlmAgent` in a `LoopAgent` (up to 3 iterations, six deterministic tools) proposes mechanic, audience and rationale.
- **Eight deterministic guardrails** (margin floor, frequency cap, consent, sell-by line, subscriber discount, open stockout, holdout, cite-or-drop) reject a play and send the reason back.
- **Vision intake.** Gemini reads SKU, printed date and facings from a pallet photo, each with a confidence; rows under 70% need a human.
- **Customer agent.** English and Kannada chat, MCP orders, STOP; held-out customers see no offer.

| The model decides | Code decides |
|---|---|
| mechanic, audience, rationale; revision after a rejection | every rupee (estimator), the eight guardrails, the holdout and its assignment |
| SKU, date and facings read from a photo | which rows need confirmation; the sell-by date (a rule) |
| dialogue and substitution reasoning | stock, eligibility, consent, order prices |

More: [`docs/gen_ai_detail.md`](docs/gen_ai_detail.md).

## Evidence

[Learning curve](docs/learning_curve.md), including changes that made a number worse. On the public retail backtest the forecaster does not beat a naive seasonal baseline (all-days WAPE 1.12 vs 0.99, [`eval/external_backtest.md`](eval/external_backtest.md)); Taal's value is the loop after the forecast. Tests are counted with `pytest --collect-only` and `playwright test --list`; `make verify` gates every pull request on the stub model backend, and a post-deploy smoke makes real model calls. Vision: 30/30 on synthetic photos (14 Oct). Pre-switch (`gemini-2.5-flash`): agent simulation 190/190, run cost ₹486. [`eval/evaluation.md`](eval/evaluation.md).

## What is real and what is simulated

- **LIVE:** Plan live (a Gemini call), chat and MCP orders, offers with consent and STOP enforced in code, holdout assignment.
- **RECORDED:** the Tea and chips plays (committed Gemini runs), sample-photo reads, stored offer copy.
- **SYNTHETIC:** the forecast history and one fictional tenant (4,000 customers, 300 SKUs, 16 nodes), and every order.

Detail: [`docs/real_vs_simulated.md`](docs/real_vs_simulated.md). Badges in the app: LIVE, REPLAY (RECORDED), SYNTHETIC. No pilot has run.

## How Taal connects to a real retailer

The write-off owner (category or dark-store operations) uses and pays. It needs stock with batch and expiry, sales history and a consented customer list; the first two load from CSVs today ([`docs/bring_your_own_data.md`](docs/bring_your_own_data.md)), customers and consent are a pilot's first step. Only opted-in customers are reachable; STOP and consent are enforced in code, designed to India's DPDP consent model (not certified). Every play needs a person's approval.

## Architecture

![Taal architecture](docs/architecture.svg)

| Service | What it decides or stores |
|---|---|
| Cloud Run `taal-web`, `taal-agents` | app and API, per-visitor sandboxes; scale to zero when idle; `max-instances` 1 |
| Vertex Gemini | proposal, photo read, chat |
| ADK 2.9.0 | the planner loop and its tools |
| Model Armor | screens chat messages and replies |
| BigQuery | nightly batch jobs and the stored offer copy (`AI.GENERATE_TABLE`); the Desk forecast is local |
| Firestore | practitioner feedback |
| MCP order tool | places the order from chat |
| Cloud Scheduler | nightly jobs; keep-warm pings during judging |

Paths: [`docs/architecture.md`](docs/architecture.md).

## Impact and limits

FSSAI's advisory of 3 Dec 2024 ([file RCD-13/1/2024-Regulatory-FSSAI(E-13150)](https://fssai.gov.in/upload/advisories/2024/12/674efa161d756Adobe%20Scan%203%20Dec%202024.pdf)) asks online food sellers to deliver with at least 30% shelf life or 45 days left: an advisory, not law. Taal plans to that online sell-by line, which can fall weeks before the printed expiry.

As reported by Inc42 (22 Jul 2026), Blinkit's inventory losses were about 1.8% of net order value (₹17,132 crore, 2,443 stores): about ₹0.5 crore per store per year (all inventory loss, one quarter annualised): context, not a Taal result.

3 of 7 practitioners we surveyed write off stock weekly or daily.

Projected margin per node (tenant ÷ 16 nodes; year = × 365/28; `portfolio_prior_sensitivity_2026-10-09.json`):

| Response prior | Per 28 days | Per year |
|---|---|---|
| 2% | ₹8,796 | ₹1.15 lakh |
| 5% | ₹21,710 | ₹2.83 lakh |
| 10% | ₹38,698 | ₹5.04 lakh |

**What it costs to run.** About ₹6.5 per planned play (`gemini-3.5-flash` list prices, 14 Oct, `eval/raw/live_eval_2026-10-14/summary.json`); offer copy is generated once and stored; services scale to zero when idle. Production path: [`docs/scale.md`](docs/scale.md).

**Fair-use limits.** Per 15 minutes: 120 plan runs, 600 chat turns and 60 photo reads shared; 20, 60 and 10 per visitor. A limit returns HTTP 429 with `Retry-After` and clears itself.

**What breaks first**
- State lives in process memory: sandboxes reset on redeploy or recycle, hence `max-instances` 1.
- `/health` reports configuration, not live probes; `make smoke-judging` checks liveness.
- Vision accuracy on real photos is unmeasured.
- A photo whose product and date are both unreadable now returns no row (the V6 fix); the operator retakes it.

[Runbook](docs/judging_runbook.md), [demo fallback](docs/demo_fallback.md). Pilot design: [`docs/pilot.md`](docs/pilot.md).

## Team and licence

Nandish (lead) and Rinu (co-builder). MIT for code (`LICENSE`); data terms in `DATA_LICENSES.md`. Setup and deploy: [`docs/development.md`](docs/development.md).
