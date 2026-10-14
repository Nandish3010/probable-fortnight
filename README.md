# Taal

Taal turns a retailer's write-off forecast into a human-approved, holdout-tested offer for the right customers.

On the live Desk: 103 packs of Darjeeling Tea, 24 days to the online sell-by, ₹35,020 at stake.

Forecast, Propose, Approve, Offer, Measure. Retail & Commerce entry, Google Cloud AI Builder Cup 2026.

| Result | Figure | Label |
|---|---|---|
| Hero play vs doing nothing | **₹9,191** recovered | PROJECTED, synthetic |
| Beat a blanket 20% markdown | **₹6,186** | PROJECTED, derived |
| Holdout | 355 treated, 39 held out; lift +0.3 pp, 95% CI -8.7 to +1.6 | inconclusive, synthetic |
| Live Plan | 22/24 Gemini-authored, p50 26.5 s | `gemini-3.5-flash`, 11 Oct |
| Approve | 1.4 to 1.7 s warm | 13 Oct, `taal-agents-00143-8v9` |
| Evalsets | 43/46 response match, 1/46 strict trajectory | 12 Oct |
| Tests | 500+ pytest, 600+ Playwright cases | `make verify` gate |

Sources: `eval/raw/tea_recorded_beat_2026-10-12.json`, `plan_live_2026-10-12.json`, `approve_timing_2026-10-13b.json`, `approve_timing_2026-10-13c.json`, `live_eval_2026-10-12/`.

## Judge quick-start

No sign-in. Each visitor has a private sandbox; Reset restores it. The demo clock is pinned to 12 Sep 2026. After idle, the first load can take about 10 s.

1. Open <https://taal-web-2obkp776ca-el.a.run.app> and click **Run the 60-second beat**. You land on the Darjeeling Tea gap: 103 units, ₹35,020 at stake, 24 days to the online sell-by.
2. Click **Approve**. The headline reads "Recovered vs doing nothing ₹9,191" (projected), with 355 customers treated and 39 held out. The play still nets -₹25,829 against ₹35,020 at stake; ₹9,191 is the gain over doing nothing.
3. Click **Chat as Ravi**, then **Send** and **Add to cart**. The offer arrives and the order total is ₹450.

Also try **Plan live** (a live Gemini re-plan, about 27 s).

| Live app | Video | Deck | Repo | API health |
|---|---|---|---|---|
| [taal-web](https://taal-web-2obkp776ca-el.a.run.app) | [Demo video (2:37)](https://drive.google.com/file/d/1vL2_t9pFg4fiMYkumUqtepM3VfA5s2a5/view?usp=sharing) | [PDF](docs/deck.pdf) | [GitHub](https://github.com/Nandish3010/probable-fortnight) | [/health](https://taal-agents-2obkp776ca-el.a.run.app/health) |

## How Gen AI is used

Gemini 3.5 Flash (`gemini-3.5-flash`) on Vertex AI in asia-south1 does the language and judgement work. The fallback `gemini-3.5-flash-lite`, on the global endpoint, runs only when the primary answers 404, 429 or 5xx (`config/models.toml`).

- **Planner.** An ADK `LlmAgent` inside a `LoopAgent` (up to 3 iterations) with six deterministic tools proposes the mechanic, audience and rationale for each at-risk lot. A rejected proposal is sent back with the reason.
- **Eight guardrails** reject a play when: its margin is under the category floor; a customer is already at the frequency cap (2 plays in 7 days); the audience lacks marketing consent; near-deadline copy lacks the sell-by line; subscribers sit in a discount audience; it pushes a SKU with an open stockout gap; the holdout is missing or invalid; or a number in the rationale appears nowhere in the play's own fields (cite-or-drop). Cite-or-drop cannot tell if a true number is cited for the right reason.
- **Vision intake.** Gemini reads a pallet photo into SKU, the date printed on the pack and facings, each with a confidence; rows under 70% need a human to confirm.
- **Customer agent.** Chat in English and Kannada (Kannada replies carry an English gloss), orders through an MCP order tool, STOP withdraws consent, and a holdout persona sees no offer.

| The model decides | Code decides |
|---|---|
| mechanic, audience, rationale; revision after a rejection | every rupee (estimator), the eight guardrails, the holdout and its assignment |
| SKU, date and facings read from a photo | which rows need confirmation; the sell-by date (a rule) |
| dialogue and substitution reasoning | stock, eligibility, consent, order prices |

Detail and the offer-copy path: [`docs/gen_ai_detail.md`](docs/gen_ai_detail.md).

## Evidence

| Measure | Result |
|---|---|
| ADK response match | **43/46 (93%)** on `gemini-3.5-flash`, 12 Oct, planner prompt v6 |
| Exact tool trajectory | **1/46**. The 46 evalsets were recorded on 28 Sep from `gemini-2.5-flash` and mostly contain 2 to 5 `propose_play` attempts (41 of 46); `gemini-3.5-flash` proposes first time in 40 of 45 cases, so exact order no longer matches |
| Post-hoc, from stored results, not a configured metric | first proposed play passed the gate in 41/46; every expected tool called 46/46; run ends with `propose_play` 46/46; IN_ORDER and ANY_ORDER match 5/46 (same retry reason) |
| Rationale judge | 15/15, mean 5.0, by a same-family judge (weak evidence) |
| Live Plan, deployed | 22 of 24 model-planned, 0 fallbacks, p50 26.5 s, p95 31.8 s (11 Oct); 2 runs lost to a cold-instance 404 count as not passed |

Prompt v6 was measured; v7, which the Tea recording uses, was not. It is a regression guard, not an accuracy score. Files: `eval/raw/live_eval_2026-10-12/` (12 Oct) and `eval/raw/plan_live_2026-10-12.json`.

**Tests, by suite:** 293 unit, 112 agents, 53 API, 31 SQL and 22 contract pytest functions (511), plus 575 e2e and 32 live Playwright cases (grep counts, 14 Oct). **CI:** `make verify` runs on every pull request; a push to `main` deploys only after it is green, then a smoke job checks health, a gap, an approve and a chat reply.

**Approve timing:** 2.1 to 2.5 s warm on `taal-agents-00141-lhz` (`approve_timing_2026-10-13b.json`), then 1.4 to 1.7 s on `taal-agents-00143-8v9` with web `taal-web-00080-72v` (`approve_timing_2026-10-13c.json`, five warm samples, not a percentile). A first call after idle is slower.

The agent simulation, vision, latency and run-cost cards ran on `gemini-2.5-flash` in September and were not re-run. Full narrative: [`docs/eval_narrative.md`](docs/eval_narrative.md), [`eval/evaluation.md`](eval/evaluation.md).

## What is real and what is simulated

| Component | Status | What it is |
|---|---|---|
| Forecast and gaps | SYNTHETIC | local forecaster over the seeded Kutumb Mart history; the judge path does not read the nightly BigQuery output |
| Plays | RECORDED, SCRIPTED | Tea (12 Oct) and chips (10 Oct) are committed Gemini runs; cola, kaju and quinoa are scripted fixtures; Plan live is a LIVE Gemini call |
| Offers | LIVE | treated customers only, consent and STOP enforced by code, on a SYNTHETIC audience |
| Orders | LIVE, SYNTHETIC | chat and the MCP order call run live; the order lands in your private sandbox |
| Holdout | LIVE, SYNTHETIC | assignment by hash is live; the result is one fast-forwarded synthetic order |
| Customers | SYNTHETIC | 4,000 customers, 300 SKUs, 16 nodes, one fictional tenant |
| Photos | SCRIPTED | eight AI-generated sample photos replay recorded reads; a real upload is live and experimental |
| Copy | RECORDED | BigQuery-generated ahead of time and stored; the validator runs live |

The app's badges are LIVE, REPLAY (RECORDED here) and SYNTHETIC. No pilot has run; the badge name `REAL PILOT` is reserved in code and unused.

## Architecture

![Taal architecture: two Cloud Run services, Gemini on Vertex AI, an MCP order tool, Firestore, nightly BigQuery jobs](docs/architecture.svg)

| Service | What it decides or stores |
|---|---|
| Cloud Run `taal-web`, `taal-agents` | the app, and the API with per-visitor sandboxes; `min-instances` 0, `max-instances` 1 |
| Vertex Gemini | the proposal, the pallet-photo read and the customer chat |
| ADK | the planner loop and its six tools |
| BigQuery | the nightly forecast job; offer copy is pre-generated with `AI.GENERATE_TABLE`, stored (`copy.source` `existing`, `copy.provenance` `bigquery_pregenerated`) and reused at Approve |
| Firestore | practitioner feedback |
| MCP order tool | places the order from chat |
| Cloud Scheduler | nightly jobs, plus keep-warm pings (`taal-agents-warm` every 5 min, `taal-web-keepwarm` every 10 min) |

Model moved off `gemini-2.5-flash` on 10 Oct 2026 (retires 20 Oct). Request paths: [`docs/architecture.md`](docs/architecture.md).

## Impact and limits

FSSAI's advisory of 3 Dec 2024 ([file RCD-13/1/2024-Regulatory-FSSAI(E-13150)](https://fssai.gov.in/upload/advisories/2024/12/674efa161d756Adobe%20Scan%203%20Dec%202024.pdf)) asks e-commerce food operators to deliver with a minimum of 30% shelf life or 45 days left. It is an advisory, not law; the either-limit reading Taal applies is its own default (`config/tenant.demo.toml`).

As reported by Inc42 (22 Jul 2026), Blinkit's inventory losses were about 1.8% of net order value (NOV). With the same article's NOV of ₹17,132 crore and 2,443 stores, ₹17,132 cr / 2,443 x 4 x 1.8% is about ₹0.5 crore per store per year. It covers all inventory loss and annualises one quarter: context, not a Taal result.

In our survey, 3 of 7 practitioners write off stock weekly or daily.

Projected margin per node (16 nodes = 10 dark stores + 6 outlets), per 28-day run, at a 2% / 5% / 10% response prior, from tenant totals of ₹1.41 / 3.47 / 6.19 lakh (₹347,356 at 5%; `portfolio_prior_sensitivity_2026-10-09.json`, `docs/impact_numbers.md`). Annualised, 28-day figure x 365/28:

| Response prior | Per node, 28-day run | Per node, per year (projected) |
|---|---|---|
| 2% | ₹8,796 | 8,796 x 365/28 = ₹114,662 (₹1.15 lakh) |
| 5% | ₹21,710 | 21,710 x 365/28 = ₹283,005 (₹2.83 lakh) |
| 10% | ₹38,698 | 38,698 x 365/28 = ₹504,456 (₹5.04 lakh) |

Projected, synthetic tenant.

**What breaks first**
- Cold start: `min-instances` is 0, so an idle service answers slowly; keep-warm pings help.
- Session and re-plan state lives in process memory and is wiped on redeploy, hence `max-instances` 1.
- All data is synthetic, and the holdout result is inconclusive.
- Offer copy is pre-generated for the seven seeded plays only; any other play tries one BigQuery call, then templates.
- Voice is not in this submission; vision accuracy on real photos is unmeasured; the ₹486 monthly run cost was measured on `gemini-2.5-flash`.

SIMULATION of the measurement design, not a result: the demo holdout is under-powered by design (n = 355/39 synthetic orders). To resolve a 5 pp lift at 80 percent power the same design needs about 1,160 orders (`eval/raw/holdout_power_2026-10-14.json`, [`docs/impact_math.md`](docs/impact_math.md)).

Runbook: [`docs/judging_runbook.md`](docs/judging_runbook.md). More: [`docs/problem_and_impact.md`](docs/problem_and_impact.md), [`docs/real_vs_simulated.md`](docs/real_vs_simulated.md), [`docs/scale.md`](docs/scale.md), [`docs/pilot.md`](docs/pilot.md) (design only, no pilot ran), [`docs/screenshots.md`](docs/screenshots.md) (pre-redesign screenshots).

## Team and licence

Nandish (lead) and Rinu (co-builder). MIT for code (`LICENSE`); third-party data terms in `DATA_LICENSES.md`.

Setup, make targets and deploy runbook: [`docs/development.md`](docs/development.md). Your CSVs: [`docs/bring_your_own_data.md`](docs/bring_your_own_data.md). More in [`docs/`](docs/).
