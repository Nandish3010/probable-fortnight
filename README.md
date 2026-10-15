# Taal

Taal turns a retailer's write-off forecast into a human-approved, holdout-tested offer for the right customers.

On the live Desk: 103 packs of Darjeeling Tea, 24 days to the online sell-by, ₹35,020 at stake.

Forecast, Propose, Approve, Offer, Measure. Retail & Commerce entry, Google Cloud AI Builder Cup 2026.

| Result | Figure | Label |
|---|---|---|
| Hero play vs doing nothing | **₹9,191** recovered | PROJECTED, synthetic |
| Beat a blanket 20% markdown | **₹6,186** | PROJECTED, derived |
| Holdout | 355 treated, 39 held out; lift +0.3 pp, 95% CI -8.7 to +1.6. A 5 pp lift needs about 1,156 customers (SIMULATION) | inconclusive, synthetic |
| Adversarial eval | 50 of 60 attack runs stopped, 0 of 18 genuine requests refused (20 attacks, 6 controls, 3 runs each, frozen). Of 4 cases that got through, 3 are fixed in code (V3 3/3, P3 3/3, C8 refused by the tool); the cropped-label case (V6) is not. [Details](eval/evaluation.md#chat-cases-at-the-shipped-setting-minimal-thinking) | MEASURED, `gemini-3.5-flash`, 14 Oct |
| Model Armor | Screens every chat message and reply; live check: an injection prompt is refused before the agent runs | MEASURED, `taal-agents-00149-sw6`, 14 Oct |
| Live Plan | 22/24 Gemini-authored, p50 26.5 s | MEASURED, `gemini-3.5-flash`, prompt v6, 11 Oct |
| Planner evalsets | First proposal accepted 39/46; strict trajectory 18/46 against same-model expectations (a regression guard, not accuracy) | MEASURED, `gemini-3.5-flash`, prompt v7, re-recorded 14 Oct |
| Approve | 1.4 to 1.7 s warm | MEASURED, 13 Oct, `taal-agents-00143-8v9` |
| Chat latency (Model Armor on) | p50 3.66 s, p95 4.36 s (was 4.24 s and 8.44 s before the stock prefetch, Model Armor client reuse and minimal thinking) | MEASURED, `gemini-3.5-flash`, 14 Oct, local API |
| Accessibility | 0 serious or critical axe findings in 20 first-paint scans | MEASURED, mock mode, 14 Oct |
| Tests | 500+ pytest, 600+ Playwright | `make verify` gate |

Every figure has a dated source in [`eval/raw/`](eval/raw/) or [`deck/claims.md`](deck/claims.md).

## Judge quick-start

No sign-in; each visitor gets a private sandbox (Reset restores it). Data is synthetic and labelled; the demo clock is pinned to 12 Sep 2026. After idle, first load takes about 10 s. Model calls have [fair-use limits](#impact-and-limits); a limit shows the retry time.

1. Open <https://taal-web-2obkp776ca-el.a.run.app> and click **Run the 60-second beat**. You land on the Darjeeling Tea gap (103 units, ₹35,020 at stake).
2. Click **Approve**: it reads "Recovered vs doing nothing ₹9,191" (projected): 355 customers treated, 39 held out. The play still nets -₹25,829; ₹9,191 is the gain over doing nothing.
3. Click **Chat as Ravi**. It asks "Any offers today?" for him and the Tea offer arrives. Click **Add to cart**: the order total is ₹450.

Then type in the chat (each checked on the live app, 15 Oct):

| You type | Expected reply |
|---|---|
| Is the Darjeeling tea in stock? | Yes, with the 100g and 250g packs and an Add to cart button |
| Do you have Cola Zero? | Yes, with the sizes in stock (synthetic catalogue prices) |
| STOP | Unsubscribed; consent removed and pending offers dropped |

Also try **Plan live** (a live Gemini re-plan, about 27 s).

| Live app | Video | Deck | Repo | API health |
|---|---|---|---|---|
| [taal-web](https://taal-web-2obkp776ca-el.a.run.app) | [Demo video (2:35)](https://drive.google.com/file/d/1hBKapntHMnc4FNybRqSEWods2MTrluBw/view?usp=sharing) | [PDF](docs/deck.pdf) | [GitHub](https://github.com/Nandish3010/probable-fortnight) | [/health](https://taal-agents-2obkp776ca-el.a.run.app/health) |

## How Gen AI is used

`gemini-3.5-flash` on Vertex AI (asia-south1) does the language and judgement work; `gemini-3.5-flash-lite` (global) runs only when the primary answers 404, 429 or 5xx (`config/models.toml`).

- **Planner.** An ADK `LlmAgent` in a `LoopAgent` (up to 3 iterations) with six deterministic tools proposes the mechanic, audience and rationale for each at-risk lot.
- **Eight deterministic guardrails** (margin floor, frequency cap, consent, sell-by line, subscriber discount, open stockout, holdout, cite-or-drop) reject a play and send the reason back to the planner.
- **Vision intake.** Gemini reads SKU, printed date and facings from a pallet photo, each with a confidence; rows under 70% need a human.
- **Customer agent.** English and Kannada chat; orders through an MCP tool; STOP withdraws consent; held-out customers see no offer.

| The model decides | Code decides |
|---|---|
| mechanic, audience, rationale; revision after a rejection | every rupee (estimator), the eight guardrails, the holdout and its assignment |
| SKU, date and facings read from a photo | which rows need confirmation; the sell-by date (a rule) |
| dialogue and substitution reasoning | stock, eligibility, consent, order prices |

Detail: [`docs/gen_ai_detail.md`](docs/gen_ai_detail.md).

## Evidence

- **ADK evalsets (14 Oct, `gemini-3.5-flash`, prompt v7):** response match 46/46, strict trajectory 18/46, first proposal accepted 39/46, against expectations re-recorded from the same model: a regression guard, not accuracy. History: 43/46 and 1/46 (12 Oct, older recordings).
- **Live Plan:** 22 of 24 model-planned, 0 fallbacks, p50 26.5 s, p95 31.8 s (11 Oct, prompt v6); 2 runs lost to a cold-instance 404 count as not passed.

**Learning curve:** [`docs/learning_curve.md`](docs/learning_curve.md) (measured, changed, re-measured, including changes that made a number worse).
On the public retail backtest the forecaster does not beat a naive seasonal baseline (all-days WAPE 1.12 vs 0.99, [`eval/external_backtest.md`](eval/external_backtest.md)); Taal's value is the loop after the forecast.

**Tests and CI:** 511 pytest functions and 607 Playwright cases (14 Oct); `make verify` gates every pull request, and `main` deploys only when green, then a smoke job runs.

Vision: 30/30 dates on synthetic photos (14 Oct, `vision_synthetic.json`). Pre-switch (`gemini-2.5-flash`): agent simulation 190/190 (21 Sep), run cost ₹486 (23 Sep). Narrative: [`docs/eval_narrative.md`](docs/eval_narrative.md), [`eval/evaluation.md`](eval/evaluation.md).

## What is real and what is simulated

| Component | Status | What it is |
|---|---|---|
| Forecast and gaps | SYNTHETIC | local forecaster over seeded Kutumb Mart history |
| Plays | RECORDED, SCRIPTED | Tea and chips are committed Gemini runs; others scripted; Plan live is LIVE |
| Offers | LIVE | treated customers only, consent and STOP enforced by code, on a SYNTHETIC audience |
| Orders | LIVE, SYNTHETIC | chat and the MCP order call run live; the order lands in your sandbox |
| Holdout | LIVE, SYNTHETIC | live hash assignment; result from one fast-forwarded synthetic order |
| Customers | SYNTHETIC | 4,000 customers, 300 SKUs, 16 nodes, one fictional tenant |
| Photos | SCRIPTED | AI-generated samples replay recorded reads; a real upload is live, experimental |
| Copy | RECORDED | BigQuery-generated ahead of time and stored; the validator runs live |

The app's badges are LIVE, REPLAY (RECORDED here) and SYNTHETIC. No pilot has run.

## Architecture

![Taal architecture](docs/architecture.svg)

| Service | What it decides or stores |
|---|---|
| Cloud Run `taal-web`, `taal-agents` | the app (the URL judges open) and the API with per-visitor sandboxes; scales to zero, `max-instances` 1 |
| Vertex Gemini | the proposal, the pallet-photo read and the customer chat |
| ADK 2.9.0 (Agent Development Kit) | the planner `LoopAgent` and its six deterministic tools |
| Model Armor | screens every customer chat message and reply for prompt injection and jailbreak |
| BigQuery | the nightly forecast job; offer copy is pre-generated with `AI.GENERATE_TABLE`, stored and reused at Approve |
| Firestore | practitioner feedback |
| MCP order tool | places the order from chat |
| Cloud Scheduler | nightly jobs, plus keep-warm pings |

Moved off `gemini-2.5-flash` on 10 Oct. Request paths: [`docs/architecture.md`](docs/architecture.md).

## Impact and limits

FSSAI's advisory of 3 Dec 2024 ([file RCD-13/1/2024-Regulatory-FSSAI(E-13150)](https://fssai.gov.in/upload/advisories/2024/12/674efa161d756Adobe%20Scan%203%20Dec%202024.pdf)) asks online food sellers to deliver with at least 30% shelf life or 45 days left: an advisory, not law.

As reported by Inc42 (22 Jul 2026), Blinkit's inventory losses were about 1.8% of net order value (₹17,132 crore, 2,443 stores): about ₹0.5 crore per store per year. All inventory loss, one quarter annualised: context, not a Taal result.

3 of 7 practitioners we surveyed write off stock weekly or daily.

Projected margin per node (tenant total ÷ 16 nodes) at three response priors (`portfolio_prior_sensitivity_2026-10-09.json`, `docs/impact_numbers.md`):

| Response prior | Per node, 28-day run | Per node, per year (projected) |
|---|---|---|
| 2% | ₹8,796 | 8,796 x 365/28 = ₹114,662 (₹1.15 lakh) |
| 5% | ₹21,710 | 21,710 x 365/28 = ₹283,005 (₹2.83 lakh) |
| 10% | ₹38,698 | 38,698 x 365/28 = ₹504,456 (₹5.04 lakh) |

**Running it.** About ₹6.5 per planned play ($0.0777, `gemini-3.5-flash` at list prices, 46 plays, 14 Oct, `eval/raw/live_eval_2026-10-14/summary.json`); offer copy is generated once and stored; both services scale to zero. Production path: [`docs/scale.md`](docs/scale.md).

**Fair-use limits.** Per 15 minutes, all visitors share 120 plan runs, 600 chat turns and 60 photo reads; each visitor gets 20, 60 and 10 (uploads up to about 20 MB). Sample photos are unlimited. A limit returns HTTP 429 with `Retry-After` and clears itself.

**What breaks first**
- Cold start: `min-instances` is 0.
- Sessions and re-plan state live in process memory (wiped on redeploy), hence `max-instances` 1.
- All data is synthetic; the holdout is inconclusive and under-powered by design (SIMULATION: a 5 pp lift needs about 1,156 customers, `eval/raw/holdout_power_2026-10-14.json`).
- Offer copy is pre-generated for the seven seeded plays only; others try one BigQuery call, then templates.
- No voice; vision accuracy on real photos is unmeasured; the ₹486 run cost is pre-switch.
- One adversarial case is open: a cropped label can still produce an invented SKU row (V6).

Runbook: [`docs/judging_runbook.md`](docs/judging_runbook.md); live-demo fallback: [`docs/demo_fallback.md`](docs/demo_fallback.md). More: [`docs/problem_and_impact.md`](docs/problem_and_impact.md), [`docs/impact_math.md`](docs/impact_math.md), [`docs/real_vs_simulated.md`](docs/real_vs_simulated.md), [`docs/pilot.md`](docs/pilot.md) (design only).

## Team and licence

Nandish (lead) and Rinu (co-builder). MIT for code (`LICENSE`); data terms in `DATA_LICENSES.md`. Setup and deploy: [`docs/development.md`](docs/development.md). Your CSVs: [`docs/bring_your_own_data.md`](docs/bring_your_own_data.md).
