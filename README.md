# Taal

Taal turns a write-off forecast into a human-approved play (a transfer, an offer or both). The agent is refused by code until its play carries a holdout; code assigns the groups, and the app says plainly when the result has not proved anything yet.

For a dark-store team clearing a lot before its online sell-by: on the live Desk, 103 packs of Darjeeling Tea, 24 days left, ₹35,020 at stake. Forecast, Propose, Approve, Offer, Measure. Retail & Commerce, AI Builder Cup 2026.

**What is new here**
- **No customer-targeted play without a holdout, enforced in code.** `rule_holdout_required` rejects a play without a holdout fraction of 5 to 90%, a minimum treated count and a seed (`agents/gate/guardrails.py:200-229`); code then sets the seed and assigns the groups (`agents/planner/tools.py:527`). Price cuts use a node holdout when one exists and say so when it does not. Statistical power is not checked.
- **It says when nothing is proved yet.** A holdout interval that crosses zero reads INCONCLUSIVE, labelled SYNTHETIC, and the power simulation states the data a real answer needs: about 1,156 customers for a 5 pp lift (`eval/raw/holdout_power_2026-10-14.json`). The ₹9,191 stays labelled PROJECTED.
- **Each safety layer measured on its own.** The tool refuses another customer's id in every run although the chat model tries it 3 of 3 times (`agents/customer/tools.py:43-59`); Model Armor blocks 3 of 8 chat injection cases (`eval/evaluation.md:1167-1172`) and fails open (`services/api/model_armor.py:7-10,98`).
- **Pre-registered evals.** Protocols are committed before any model call; a fallback-model answer voids the run. On 36 sealed scenarios from an unseen tenant, approved plays beat a blanket 20% markdown in 29 (16 of 23 where the markdown is profitable): our line of 30 was missed. 0 rule violations reached Approve (`eval/sealed/PROTOCOL.md`).
- **Cite-or-drop that resists tricks.** Rationale numbers must match the play in Western or Indian digit grouping (`agents/gate/guardrails.py:309-316`); copied untrusted phrases are caught after folding look-alike and invisible characters (`agents/gate/untrusted.py:18-38`).

**Why us.** We are in a category team at Supertails, an Indian pet-care e-commerce company: Nandish on pricing, Rinu on online sales and part of the P&L. Near-expiry and slow-moving stock is a standing cost: written off, or tying up storage and capital. Phase 1 is near-expiry stock; phase 2, slow-moving SKUs. Taal has not been used at Supertails; all data is synthetic.

| Result | Figure | Label |
|---|---|---|
| Sealed baseline eval | beats a blanket 20% markdown 29/36; 16/23 where the markdown is profitable (line 30: missed); 0 rule violations; deadlines 3 to 14 days, 21 of 36 from neighbouring cells | MEASURED, 19 Oct; projected, synthetic |
| Hero play vs doing nothing | Transfer to the outlet that can sell the tea plus a targeted nudge: **₹9,191** projected recovery (₹9,397 waste avoided minus ₹206 transfer cost) | PROJECTED, synthetic |
| Beat a blanket 20% markdown | **₹6,186** | PROJECTED, derived |
| Holdout | 355 treated, 39 held out; +0.3 pp, 95% CI -8.7 to +1.6; a 5 pp lift needs about 1,156 customers (SIMULATION) | inconclusive, synthetic |
| Adversarial eval | 50 of 60 attack runs stopped, 0 of 18 genuine requests refused. 10 runs (4 cases) got through; V3, P3, V6 since fixed and re-ran 3/3 (V6 threshold set after the frozen run); C8: the model still tries, the tool refuses every run. [Details](eval/evaluation.md#hardening-16-oct-2026) | MEASURED, 14 and 16 Oct |
| Model Armor | Screens every chat message and reply; verified live; fails open, code guardrails still apply | MEASURED, 14 Oct |
| Planner evalsets | First proposal accepted 39/46; strict trajectory 18/46 against same-model recordings (a regression guard, not accuracy) | MEASURED, prompt v7, 14 Oct |
| Approve | 1.4 to 1.9 s warm (recorded play, no model call) | MEASURED, 13 to 15 Oct |
| Chat latency (Model Armor on) | p50 3.66 s, p95 4.36 s | MEASURED, 14 Oct, local API |
| Accessibility | no serious or critical axe issues | mock mode, 14 Oct |
| Tests | 870 pytest, 833 Playwright (+34 live) | collected, 16 Oct |

Sources: [`eval/raw/`](eval/raw/).

## Judge quick-start

No sign-in; each visitor gets a private sandbox. Synthetic data, demo clock 12 Sep 2026; after idle, first load takes about 10 s. Model calls have [fair-use limits](#impact-and-limits).

1. Open <https://taal-web-2obkp776ca-el.a.run.app> and click **Run the 60-second beat**. You land on the Darjeeling Tea gap.
2. Click **Approve**: it reads "Recovered vs doing nothing ₹9,191" (projected): 355 customers treated, 39 held out.
3. Click **Chat as Ravi**. It asks "Any offers today?" for him and the Tea offer arrives. Click **Add to cart**: the order total is ₹450.

Then type (tested 15 Oct):

| You type | Expected reply |
|---|---|
| Is the Darjeeling tea in stock? | Yes: 100g and 250g packs, with Add to cart |
| Do you have Cola Zero? | Yes: the sizes in stock (synthetic prices) |
| STOP | Unsubscribed; pending offers dropped |

Also try **Plan live** (a live Gemini re-plan, about 27 s).

| Live app | Video | Deck | Repo | Configuration check |
|---|---|---|---|---|
| [taal-web](https://taal-web-2obkp776ca-el.a.run.app) | [Demo video (3:14)](https://drive.google.com/file/d/1hBKapntHMnc4FNybRqSEWods2MTrluBw/view?usp=sharing) | [PDF](docs/deck.pdf) | [GitHub](https://github.com/Nandish3010/probable-fortnight) | [/health](https://taal-agents-2obkp776ca-el.a.run.app/health) |

## How Gen AI is used

`gemini-3.5-flash` on Vertex AI does the language and judgement work; `gemini-3.5-flash-lite` is the fallback on 404, 429 or 5xx. The forecast is a deliberately simple baseline (it loses to a naive seasonal one); BigQuery runs the nightly batch and stored copy.

- **Planner.** An ADK `LlmAgent` in a `LoopAgent` (up to 3 iterations, six deterministic tools) proposes mechanic, audience and rationale.
- **Eight deterministic guardrails** (margin floor, frequency cap, consent, sell-by line, subscriber discount, open stockout, holdout, cite-or-drop) reject a play and send the reason back.
- **Vision intake.** Gemini reads SKU, printed date and facings from a pallet photo, each with a confidence; rows under 70% need a human.
- **Customer agent.** English and Kannada chat, MCP orders, STOP; held-out customers see no offer.

| The model decides | Code decides |
|---|---|
| mechanic, audience, rationale; revision after a rejection | every rupee (estimator), the eight guardrails, the holdout and its assignment |
| SKU, date and facings read from a photo | which rows need confirmation; the sell-by date (a rule) |
| dialogue and substitution reasoning | stock, eligibility, consent, order prices |

[`docs/gen_ai_detail.md`](docs/gen_ai_detail.md).

## Evidence

[Learning curve](docs/learning_curve.md), with the changes that made a number worse. Public backtest: WAPE 1.12 vs 0.99 for naive seasonal ([`eval/external_backtest.md`](eval/external_backtest.md)). `make verify` gates every pull request on the stub backend; a post-deploy smoke makes real model calls. Vision: 30/30 synthetic photos. [`eval/evaluation.md`](eval/evaluation.md).

## What is real and what is simulated

- **LIVE:** Plan live (a Gemini call), chat and MCP orders, offers with consent and STOP enforced in code, holdout assignment.
- **RECORDED:** the Tea and chips plays (committed Gemini runs), sample-photo reads, stored offer copy.
- **SYNTHETIC:** the forecast history and one fictional tenant (4,000 customers, 300 SKUs, 16 nodes), and every order.

Detail: [`docs/real_vs_simulated.md`](docs/real_vs_simulated.md). App badges: LIVE, REPLAY, SYNTHETIC. No pilot has run.

## How Taal connects to a real retailer

The write-off owner (category or dark-store operations) uses and pays. It needs stock with batch and expiry, sales history and a consented customer list; the first two load from CSVs today ([`docs/bring_your_own_data.md`](docs/bring_your_own_data.md)), customers and consent are a pilot's first step. Only opted-in customers are reachable; STOP and consent are enforced in code. Every play needs a person's approval.

## Architecture

![Taal architecture](docs/architecture.svg)

| Service | What it decides or stores |
|---|---|
| Cloud Run `taal-web`, `taal-agents` | app and API, per-visitor sandboxes; scale to zero when idle; `max-instances` 1 |
| Vertex Gemini | proposal, photo read, chat |
| ADK 2.9.0 | the planner loop and its tools |
| Model Armor | screens chat messages and replies |
| BigQuery | nightly batch and stored offer copy (`AI.GENERATE_TABLE`) |
| Firestore | practitioner feedback |
| MCP order tool | places the order from chat |
| Cloud Scheduler | nightly jobs; keep-warm pings during judging |

More: [`docs/architecture.md`](docs/architecture.md).

## Impact and limits

FSSAI's advisory of 3 Dec 2024 ([file RCD-13/1/2024-Regulatory-FSSAI(E-13150)](https://fssai.gov.in/upload/advisories/2024/12/674efa161d756Adobe%20Scan%203%20Dec%202024.pdf)) asks online food sellers to deliver with at least 30% shelf life or 45 days left: an advisory, not law. Taal plans to the online sell-by line, weeks before printed expiry.

As reported by Inc42 (22 Jul 2026), Blinkit's inventory losses were about 1.8% of net order value (₹17,132 crore, 2,443 stores): about ₹0.5 crore per store per year (all inventory loss, a quarter annualised): context, not a Taal result.

3 of 7 surveyed practitioners write off stock weekly or daily.

Projected margin per node (tenant ÷ 16 nodes; year = × 365/28; `portfolio_prior_sensitivity_2026-10-09.json`):

| Response prior | Per 28 days | Per year |
|---|---|---|
| 2% | ₹8,796 | ₹1.15 lakh |
| 5% | ₹21,710 | ₹2.83 lakh |
| 10% | ₹38,698 | ₹5.04 lakh |

**What it costs to run.** About ₹6.5 per planned play (`gemini-3.5-flash` list prices, 14 Oct); offer copy is generated once and stored; services scale to zero when idle. Production path: [`docs/scale.md`](docs/scale.md).

**Fair-use limits.** Per 15 minutes: 120 plan runs, 600 chat turns and 60 photo reads shared; 20, 60 and 10 per visitor. A limit returns HTTP 429 with `Retry-After` and clears itself.

**What breaks first**
- State lives in process memory: sandboxes reset on redeploy or recycle, hence `max-instances` 1.
- `/health` is a configuration check; `make smoke-judging` checks liveness.
- Real-photo vision: unmeasured.
- C8: chat tries a cross-customer call; the tool refuses it.

[Runbook](docs/judging_runbook.md), [demo fallback](docs/demo_fallback.md). Pilot design: [`docs/pilot.md`](docs/pilot.md).

## Team and licence

Nandish (lead) and Rinu (co-builder). MIT for code (`LICENSE`); data terms in `DATA_LICENSES.md`. Setup and deploy: [`docs/development.md`](docs/development.md).
