# Taal

Taal turns a write-off forecast into a human-approved play (a transfer, an offer or both). Code refuses a customer-targeted play without a holdout and says plainly when a result has not proved anything yet. On the live Desk: 103 packs of Darjeeling Tea, 24 days to the online sell-by, ₹35,020 at stake. Retail & Commerce, AI Builder Cup 2026.

**What is new here**
- **No customer-targeted play without a holdout, enforced in code.** `rule_holdout_required` needs a 5 to 90% holdout, a minimum treated count and a seed (`agents/gate/guardrails.py:200-229`); code assigns the groups. Price cuts use a node holdout when one exists, else say they cannot be measured. Power is not checked.
- **It says when nothing is proved yet.** An interval crossing zero reads INCONCLUSIVE; a power simulation says a 5 pp lift needs about 1,156 customers. The ₹9,191 stays PROJECTED.
- **Replay on real data (anonymised; past data, not a pilot).** First row of the results table; [detail and limits](#replay-on-real-data).
- **Each safety layer measured on its own.** The tool refuses another customer's id every run though the model tries it 3 of 3 times; Model Armor blocks 3 of 8 chat injection cases and fails open (`eval/evaluation.md`).
- **Pre-registered evals.** Protocols are committed before any model call. Sealed v1, 36 scenarios: 29 beat a blanket 20% markdown, our line of 30 missed. With the markdown option, 36 new: 17 of 18 beatable won, markdown chosen in 14 of 15 where best, 0 rule violations; 2 of 7 lines missed (net vs a blanket below the margin floor; p50 31.3 s vs 30 s) (`eval/sealed/PROTOCOL_v3.md`).
- **Cite-or-drop that resists tricks.** Rationale numbers must match the play (Western or Indian digit grouping); copied untrusted phrases are caught after folding look-alike characters (`agents/gate/untrusted.py`).

**Why us.** We are in a category team at an Indian pet-care e-commerce company: Nandish on pricing, Rinu on online sales and part of the P&L. Near-expiry and slow-moving stock is a standing cost (write-offs, or tied-up storage and capital); phase 1 is near-expiry, phase 2 slow-moving SKUs. The live demo runs on a synthetic tenant; the replay below used the company's past data, not a live pilot.

| Result | Figure | Label |
|---|---|---|
| Replay on real data (anonymised, 11 weeks) | would have flagged 99% of expiry pull-outs a median 30 days ahead; precision 45%; estimated recovery ₹8 to 15 L, about 2x a blanket markdown; a 60-days-of-stock rule fires about as early | MEASURED (flags), ESTIMATED (value); replay, not a pilot |
| Sealed baseline eval | v1: 29/36 beat a blanket 20% markdown (line 30 missed); with the markdown option 17 of 18 beatable, 0 rule violations; a 20% cut is below the margin floor everywhere | MEASURED, 19 Oct; projected, synthetic |
| Hero play vs doing nothing | Transfer to the outlet that sells the tea plus a targeted nudge: **₹9,191** projected (₹9,397 waste avoided minus ₹206 transfer) | PROJECTED, synthetic |
| Beat a blanket 20% markdown | **₹6,186** | PROJECTED, derived |
| Holdout | 355 treated, 39 held out; +0.3 pp, 95% CI -8.7 to +1.6; a 5 pp lift needs about 1,156 customers (SIMULATION) | inconclusive, synthetic |
| Adversarial eval | 50 of 60 attack runs stopped, 0 of 18 genuine requests refused (20 attacks, 6 controls, 3 runs). 10 runs (4 cases) got through; V3, P3, V6 since fixed and re-ran 3/3 (V6 threshold set after the frozen run); C8: the model still tries, the tool refuses every run. [Details](eval/evaluation.md#hardening-16-oct-2026) | MEASURED, 14 and 16 Oct |
| Planner evalsets | First proposal accepted 39/46; response match 46/46; strict trajectory 18/46 against same-model recordings (a regression guard, not accuracy) | MEASURED, `gemini-3.5-flash`, prompt v7, re-recorded 14 Oct |
| Approve | 1.4 to 1.9 s warm (10 samples; recorded play, no model call) | MEASURED, 13 to 15 Oct, `taal-agents-00155-drd` |
| Chat latency; Model Armor on (verified live; fails open) | p50 3.66 s, p95 4.36 s | MEASURED, `gemini-3.5-flash`, 14 Oct, local API |
| Accessibility | no serious or critical axe issues | MEASURED, mock mode, 14 Oct |
| Tests | 870 pytest, 833 Playwright (+34 live) | collected, 16 Oct; `make verify` gate |

Sources: [`eval/raw/`](eval/raw/).

## Replay on real data

On 3 months of real data from a pet-care e-commerce company, about ₹44.5 L of stock was pulled at the expiry cut-off in 11 weeks, roughly ₹2 crore a year (INFERRED, annualised: 11-week base, same rate all year, ignores seasonality). Replaying each week, Taal would have flagged 99% of it a median 30 days before the cut-off (MEASURED), and its transfer-or-markdown choice would have recovered an estimated ₹8 to 15 L in those 11 weeks, about twice a blanket markdown (ESTIMATED). Precision 45% (MEASURED: flagged lots whose cut-off fell inside the window and were later pulled). A 60-days-of-stock rule fires at about the same time, so Taal's value is sizing the shortfall and choosing the action, not timing. Past data, not a live pilot; aggregates only. Detail: [`docs/real_data_replay.md`](docs/real_data_replay.md). Limits:
- Expiry loss is inferred from stock leaving sellable inventory; it cannot separate destruction, returns booked elsewhere or miscounts.
- Recall is flattered: the flag and the label both come from the same sales signal.
- 11 weeks of data; only about 1,950 flagged lots reached their cut-off inside the window.
- Values are modelled: price response from promo days, extrapolated to deeper discounts; transfers at ₹40 a unit; margin on rescued stock ignored.

## Judge quick-start

No sign-in; private sandbox per visitor; synthetic data; first load after idle takes about 10 s.

1. Open <https://taal-web-2obkp776ca-el.a.run.app> and click **Run the 60-second beat**. You land on the Darjeeling Tea gap.
2. Click **Approve**: it reads "Recovered vs doing nothing ₹9,191" (projected): 355 customers treated, 39 held out.
3. Click **Chat as Ravi**. It asks "Any offers today?" for him and the Tea offer arrives. Click **Add to cart**: the order total is ₹450.

Then type (tested 15 Oct): "Is the Darjeeling tea in stock?" (two packs, Add to cart); "Do you have Cola Zero?" (sizes in stock, synthetic prices); "STOP" (unsubscribed). Also try **Plan live** (a live Gemini re-plan).

| Live app | Video | Deck | Repo | Configuration check |
|---|---|---|---|---|
| [taal-web](https://taal-web-2obkp776ca-el.a.run.app) | [Demo video (3:31)](https://drive.google.com/file/d/1hBKapntHMnc4FNybRqSEWods2MTrluBw/view?usp=sharing) | [PDF](docs/deck.pdf) | [GitHub](https://github.com/Nandish3010/probable-fortnight) | [/health](https://taal-agents-2obkp776ca-el.a.run.app/health) |

## How Gen AI is used

`gemini-3.5-flash` on Vertex AI does the language and judgement work; `gemini-3.5-flash-lite` is the fallback on 404, 429 or 5xx. The forecast is a deliberately simple baseline; Taal adds the decide, approve, measure loop.

- **Planner.** An ADK `LlmAgent` in a `LoopAgent` (up to 3 iterations, six tools) proposes mechanic, audience and rationale.
- **Eight guardrails** (margin floor, frequency cap, consent, sell-by line, subscriber discount, open stockout, holdout, cite-or-drop) plus a beats-the-best-legal-markdown check reject a play and return the reason.
- **Vision intake.** Gemini reads SKU, printed date and facings from a pallet photo, each with a confidence; rows under 70% need a human.
- **Customer agent.** English and Kannada chat, MCP orders, STOP; held-out customers see no offer.

Code, not the model, decides every rupee, the guardrails, the holdout and its assignment, stock, consent and order prices. [`docs/gen_ai_detail.md`](docs/gen_ai_detail.md).

## Evidence

[Learning curve](docs/learning_curve.md). Backtest: WAPE 1.12 vs 0.99 for naive seasonal ([`eval/external_backtest.md`](eval/external_backtest.md)); vision 30/30 synthetic photos ([`eval/evaluation.md`](eval/evaluation.md)).

## What is real and what is simulated

- **LIVE:** Plan live, chat and MCP orders, consent and STOP in code, holdout assignment.
- **RECORDED:** the Tea and chips plays, sample-photo reads, stored offer copy.
- **SYNTHETIC:** one fictional tenant (4,000 customers, 300 SKUs, 16 nodes) and every order.

[Detail](docs/real_vs_simulated.md). No live pilot has run; the replay used past data.

## How Taal connects to a real retailer

The write-off owner (category or dark-store operations) pays. It needs stock with batch and expiry, sales history and a consented customer list; the first two load from CSVs today ([`docs/bring_your_own_data.md`](docs/bring_your_own_data.md)), customers and consent are a pilot's first step. Only opted-in customers are reachable; STOP and consent are enforced in code (DPDP-designed, not certified). Every play needs approval.

## Architecture

![Taal architecture](docs/architecture.svg)

Cloud Run (`taal-web`, `taal-agents`; scale to zero; `max-instances` 1), Vertex Gemini, ADK 2.9.0, Model Armor, BigQuery, Firestore, MCP orders, Cloud Scheduler.

[Detail](docs/architecture.md).

## Impact and limits

FSSAI's advisory of 3 Dec 2024 ([RCD-13/1/2024-Regulatory-FSSAI(E-13150)](https://fssai.gov.in/upload/advisories/2024/12/674efa161d756Adobe%20Scan%203%20Dec%202024.pdf)) asks online food sellers to deliver with at least 30% shelf life or 45 days left: an advisory, not law. Taal plans to that online sell-by line, which can fall weeks before the printed expiry.

As reported by Inc42 (22 Jul 2026), Blinkit's inventory losses were about 1.8% of net order value: about ₹0.5 crore per store a year (all inventory loss, a quarter annualised); context, not a Taal result.

3 of 7 practitioners surveyed write off weekly or daily.

Projected margin per node (tenant ÷ 16 nodes; year = × 365/28; `portfolio_prior_sensitivity_2026-10-09.json`), by response prior: 2%: ₹8,796 per 28 days, ₹1.15 lakh a year; 5%: ₹21,710, ₹2.83 lakh; 10%: ₹38,698, ₹5.04 lakh.

**What it costs to run.** About ₹6.5 per planned play (`gemini-3.5-flash` list prices, 14 Oct). Production path: [`docs/scale.md`](docs/scale.md).

**Fair-use limits.** Per 15 minutes: 120 plans, 600 chat turns, 60 photo reads shared; 20, 60, 10 per visitor.

**What breaks first**
- State lives in process memory: sandboxes reset on redeploy or recycle, hence `max-instances` 1.
- `/health` checks configuration; `make smoke-judging` checks liveness.
- Real-photo vision unmeasured.
- C8: chat tries a cross-customer call; the tool refuses it.

[Runbook](docs/judging_runbook.md), [pilot design](docs/pilot.md).

## Team and licence

Nandish (lead) and Rinu (co-builder). MIT for code (`LICENSE`); data terms in `DATA_LICENSES.md`. Setup: [`docs/development.md`](docs/development.md).
