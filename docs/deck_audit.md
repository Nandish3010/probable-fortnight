# Deck audit — every checkable claim in all 12 slides, verified against the repo

Deck: `docs/deck.pdf` (exported from the working slide deck). Repo at commit
`de1fe38` when this audit started; fixes in this same branch on top of it. Every row below was
independently re-verified for this audit (code read, or a command actually run), including the
three items flagged before the audit began.

Verdicts: **TRUE**, **OVERCLAIM** (code does less than claimed), **UNDERCLAIM** (code does more
than the deck sells it as), **STALE** (was true, superseded by a later commit/measurement).

## Post-audit revision: two slides redesigned, not just corrected

Two more problems surfaced after this audit's first pass, both about the deck's *credibility*
rather than a specific factual claim, both raised directly rather than found by this process:

- **Slide `summary`** originally organized its own content under literal rubric headers
  ("Technical Merit & Gen AI", "Problem Alignment & Impact", etc.) — scoring the pitch against
  the judges' own rubric before they do. That is the judges' job, not the presenter's, and reads
  as optimizing for the rubric rather than describing the system. Replaced with a plain "what it
  does" summary of the six-step loop plus one real number, no rubric labels anywhere.
- **Slide `innovation`**'s original comparison table listed four named competitor products
  (a markdown-optimisation vendor, a demand-planning suite, Gemini Enterprise for CX, Meta
  Business Agent) with an identical "No/No/No" row for every single one. That pattern — every
  competitor scoring the same on every dimension — reads as unsubstantiated rather than analyzed,
  and none of those "No" claims were ever independently verified (they were about products
  outside this repo, not something this audit's methodology could check). Replaced with three
  claims about Taal's own mechanisms only, each already independently verified true elsewhere in
  this audit (the legal deadline as a forecast covariate, the domain-agnostic Play schema, the
  estimator that learns from measurement) — nothing asserted about any other product.

## Second revision: clarity fixes and a new architecture slide

After review, three more things were fixed, none of them factual-claim errors:

- **Slide `loop`** tried to cover both "one schema, two domains" and "two closed feedback loops"
  in one dense stack of cards with no actual visual loop -- unclear which claim it was making.
  Split: `loop` now covers only the domain-agnostic claim (its one truly distinct point), and the
  feedback-loop mechanics moved to the new `architecture` slide below, where they're shown as an
  explicit step-6-feeds-back-into-step-3 flow instead of two disconnected boxes.
- **Slide `impact`** repeated the exact same before/after number already shown on `summary`,
  adding little beyond restating it. Replaced with the real three-way comparison the estimator
  and the live sweep actually produced for this lot: do nothing (₹9,200, estimator projection),
  blanket 20% markdown (₹8,189, estimator counterfactual), and this play live-approved (₹9,194 ->
  ₹8,068, the real re-forecast) -- three different real numbers from two different real sources
  (`fixtures/golden_runs/run_chips_ds07_v1_bd0a8253.jsonl` for the first two, the same live sweep
  as before for the third), clearly labelled as such rather than presented as directly comparable
  on the same footing.
- **New slide `architecture`**, inserted after `technical`: a genuinely detailed walk through the
  six-step loop naming exactly which agent or model runs each step, its real tool-call sequence
  (`get_gap` -> `get_candidate_audiences` -> `estimate_outcomes` -> `check_guardrails` ->
  `propose_play`, with `get_past_plays` for prior evidence), where data lives (BigQuery vs
  Firestore vs the 3-file ingestion contract), and where the ML actually runs today vs what's
  been verified but isn't in production yet (same local-model-vs-BigQuery distinction as the
  Phase 2 fix above, stated once more here for a reader who only reads this slide).

## Third revision: one real diagram instead of two thin ones

The two flowchart slides added in the second revision were dropped and replaced with a single
denser diagram (`system-diagram.html`) after review: subgraph boundaries (Sense, Planner Loop,
Engage), a real decision-diamond shape for `check_guardrails`, each of the Planner's six tools as
its own node, and three distinct edge treatments (solid teal = the live request path, dashed
amber = the estimator-priors feedback into the next Planner run, dashed red = a failed guardrail
sending a draft back to revise). Same underlying facts as the second revision's two slides,
denser and closer to how a real system diagram reads.

## Summary

- 3 OVERCLAIM, 1 STALE found and fixed in the deck (Phase 2), plus the 2 credibility redesigns, 3 clarity fixes, and the diagram consolidation above.
- 1 of the OVERCLAIMs (BigQuery forecasting) was also partly closed by fixing and actually running
  the SQL against real BigQuery for one series (Phase 3) — see `eval/evaluation.md`'s new
  "Real BigQuery `ARIMA_PLUS_XREG` forecast" section and
  `eval/raw/bigquery_arima_xreg_forecast_2026-09-23.json`.
- Everything else checked TRUE against current code, with two caveats noted inline (Sense
  throughput run-to-run variance; the FSSAI regulation text itself, inherited from the project's
  own earlier research, not re-verified against a primary government source this round).

## Slide `cover`

| Claim as written | What the code does | Verdict | Fix |
|---|---|---|---|
| Live URL `taal-web-2obkp776ca-el.a.run.app` | Matches `README.md`'s own judge quick-start URL exactly | TRUE | none |
| "Kutumb Mart · 10 dark stores, 6 outlets, Bengaluru" | `data.generator` output, regenerated for this audit: `Counter({'dark_store': 10, 'outlet': 6})`, 16 nodes total | TRUE | none |

## Slide `summary`

| Claim as written | What the code does | Verdict | Fix |
|---|---|---|---|
| "BigQuery **AI.FORECAST** / **ARIMA_PLUS_XREG**" (Technical Merit card, first thing named) | `jobs/sense/forecast.py` runs a local Python seasonal model; `model` column literally says `local_seasonal_xreg`. The BigQuery SQL under `data/bigquery/sense/` had never executed before this session's Phase 3 work. `README.md` already discloses this; the deck did not. | **OVERCLAIM** | Reworded to name the local model, the BigQuery SQL as written-and-now-verified-runnable, and the one real series it has actually forecast (Phase 3) |
| "ADK Planner (LoopAgent + 8 deterministic guardrails)" | `agents/gate/guardrails.py` defines exactly 8 rule functions (`rule_margin_floor`, `rule_frequency_cap`, `rule_consent_required`, `rule_sellby_disclosure`, `rule_subscription_protect`, `rule_no_cannibalise_stockout`, `rule_holdout_required`, `rule_cite_or_drop`) | TRUE | none |
| "vision intake for pallet photos" | `agents/capture/vision.py`; live-verified earlier this project (a real upload produced a genuine `gemini-2.5-flash` vision call) | TRUE | none |
| "₹9,194 to ₹8,068 on the seeded tenant" | `eval/raw/sweep_vertex_2026-09-21.txt:12`: `writeoff 9194.12->8067.53`, a real live `/approve` call | TRUE | none |
| "One Play schema runs grocery write-off and apparel unmet-demand through identical guardrails" | `agents/gate/store.py`, `agents/planner/drafting.py` handle `assortment_gap` through the same `propose_play`/guardrail path as grocery gap types; verified no domain-specific branching in `guardrails.py`/`estimator.py` | TRUE | none |
| "every Measure run updates the estimator from real evidence" | `jobs/measure/run.py:140-147` calls `update_prior()` and writes `estimator_priors` from real treated/responder counts | TRUE | none |
| UX card: judge mode, per-visitor sandbox, LIVE/REPLAY badges | `services/api/sandbox.py` exists and implements the per-visitor isolation | TRUE | none |

## Slide `hook`

| Claim as written | What the code does | Verdict | Fix |
|---|---|---|---|
| "20 days on the pack. 6 days to sell it online." | Real generated batch `B-CHIPS-DS07-01`: `expiry_date: 2026-10-15`, as-of `2026-09-12` = **33 days**, not 20. `README.md` already states 33 days correctly. The "20 days" figure was a stray leftover from an early, since-superseded internal draft (the same conflict the project's own history once flagged as unresolved between 20/33/51-day drafts — 33 is the one the current generator and README actually produce). | **STALE / OVERCLAIM** | Changed to "33 days on the pack. 6 days to sell it online." to match README and the real generated data exactly |
| "30% of shelf life or 45 days ... online" | Matches `README.md`'s FSSAI framing and `config/tenant.demo.toml`'s `sellby_rule` | TRUE (the regulation text itself is inherited from the project's earlier research, not re-verified against a primary government source in this audit round) | none |
| "368 units ... ₹9,200 at stake" | `fixtures/golden_runs/run_chips_ds07_v1_bd0a8253.jsonl`: `units: 368`, `do_nothing_inr: 9200.0` | TRUE | none |
| "online sell-by in 6 days" | Batch `online_sellby_date: 2026-09-18`, as-of `2026-09-12` = 6 days | TRUE | none |

## Slide `loop`

| Claim as written | What the code does | Verdict | Fix |
|---|---|---|---|
| "8 deterministic guardrails" | Repeated from `summary`; verified | TRUE | none |
| Estimator: "Beta-Binomial" | `agents/gate/estimator.py` docstring: "Response rate ... ~ Beta(alpha, beta)"; real Beta-quantile math implemented | TRUE | none |
| "no domain-specific code in either" | Grepped `guardrails.py`/`estimator.py` for gap-type branching — none found | TRUE | none |
| "Approve ... writes into `future_regressors`, re-forecasts immediately" | Matches the documented `/approve` flow (README, `services/api`) | TRUE | none |
| "every run calls `update_prior()`" | Repeated from `summary`; verified | TRUE | none |

## Slide `technical`

| Claim as written | What the code does | Verdict | Fix |
|---|---|---|---|
| "Sense (nightly, BigQuery) — AI.FORECAST + ARIMA_PLUS_XREG" | Same as the `summary` finding | **OVERCLAIM** | Reworded, same fix as `summary` |
| "Planner ... 6 tools" | `agents/planner/tools.py` exposes exactly 6 agent-facing tools: `get_gap`, `get_candidate_audiences`, `get_past_plays`, `estimate_outcomes`, `check_guardrails`, `propose_play` | TRUE | none |
| "Approve (Cloud Run)" | `infra/deploy.sh` deploys `taal-agents` (which hosts `/approve`) to Cloud Run | TRUE | none |
| "Customer / Stylist Agent + Measure" box | Matches real components | TRUE | none |
| Latency table: chat p50 5.20 s / p95 7.20 s | This is `eval/raw/customer_latency_summary_2026-09-21.json` — the run **before** the `get_customer_context` prefetch fix, with 1/50 calls erroring. The post-fix run (`eval/raw/customer_latency_fix_summary_2026-09-21.json`, 50/50 OK) measured p50 **4.40 s**, p95 **5.75 s**. | **STALE** | Updated table to 4.40 s / 5.75 s |
| "Approve → re-forecast 8.30 s" | `eval/raw/sweep_vertex_2026-09-21.txt:12`: `8.3s POST /approve` | TRUE | none |
| "Sense, 300 SKUs × 16 nodes: 3.83 s" | `eval/raw/sense_throughput_2026-09-20.json`, cited correctly. **Caveat found this round:** re-running `make generate && python -m jobs.sense` today measured 4.96 s total (forecast 3.69 s vs the cited 2.50 s) — real run-to-run variance on this shared sandbox. The deck's number traces to a real committed file, so left as-is per "every number traces to a file under `eval/raw/`," but the variance is noted here for anyone re-measuring. | TRUE (with noted variance) | none |
| "50 real chat calls against Gemini 2.5 Flash on Vertex" | Matches both the pre- and post-fix methodology | TRUE | none |

## Slide `gemini`

| Claim as written | What the code does | Verdict | Fix |
|---|---|---|---|
| "Gemini decides" list (mechanic/audience/rationale, revision, vision reads, dialogue, copy) | Matches `agents/planner`, `agents/capture/vision.py`, `agents/customer`, `agents/stylist`, `jobs/sense/copy.py` | TRUE | none |
| "Deliberately never LLM" list (every rupee, all 8 guardrails, holdout hash, stock/eligibility/prices, lift/CI/measurement) | Matches `agents/gate/estimator.py`, `agents/gate/guardrails.py`, `jobs/measure/run.py` | TRUE | none |
| "The trace panel shows ... a guardrail returning `passed: false`, and the exact next tool call" | `fixtures/golden_runs/run_chips_ds07_v1_bd0a8253.jsonl` shows exactly this: the coupon draft rejected for `margin_floor`, then a bundle draft proposed next | TRUE | none |

## Slide `innovation`

| Claim as written | What the code does | Verdict | Fix |
|---|---|---|---|
| Taal row: "Sees the legal sell-by deadline? / Closes the loop into the forecast? / One schema, multiple domains?" — all Yes | All three independently verified true above (hook slide, summary slide, loop slide findings) | TRUE | none |
| Competitor rows (markdown vendor, planning suite, Gemini Enterprise for CX, Meta Business Agent) — all No | Subjective competitive positioning about external products, not a claim this repo's code can verify either way; standard competitive-comparison framing, not a checkable code claim | N/A (not code-checkable) | none |
| "Not a fourth marketing channel" / "Grounded, not general chat" | Matches `agents/customer/prompts/customer.md`'s explicit "never promise a product the stock tool did not confirm" instruction | TRUE | none |

## Slide `impact`

| Claim as written | What the code does | Verdict | Fix |
|---|---|---|---|
| "₹9,194 → ₹8,068 ... measured live against real Vertex" | Same `eval/raw/sweep_vertex_2026-09-21.txt` source as `summary` | TRUE | none |
| "FSSAI online sell-by rule already exists" | Consistent with the project's established framing throughout; not re-verified against a primary government source in this audit round | TRUE (inherited, not newly re-verified) | none |
| "STOP withdraws it immediately, checked on every future play, not just at signup" | `rule_consent_required` re-runs on every `propose_play` call, not only at signup; `record_stop` writes the withdrawal | TRUE | none |
| "the Outcomes screen labels every row REAL PILOT or SYNTHETIC and shows **unmeasured**" | `web/app/outcomes/page.tsx`: `data_label` field, explicit "unmeasured" rendering below `min_treated_n` | TRUE | none |

## Slide `evaluation`

| Claim as written | What the code does | Verdict | Fix |
|---|---|---|---|
| "Agent Simulation, guardrail pass — 190/190 — live Vertex, 5 guardrails, **200 personas**" | `eval/raw/agent_simulation_2026-09-21.json`: `n_personas: 190`, `n_pass: 190`. The evaluation table and evaluation.md both already correctly say 190 (not 200) — this was purely a deck-authoring error, not a repo-level one. | **OVERCLAIM** | "200" changed to "190" |
| "Vision read accuracy, 30 photos — 30/30, synthetic photos" | `eval/raw/vision_synthetic_2026-09-21.json`, matches `eval/evaluation_table.md` row 11 exactly | TRUE | none |
| "Customer chat p50/p95 — 5.20 s / 7.20 s" | Same staleness as the `technical` slide finding | **STALE** | Updated to 4.40 s / 5.75 s |
| "Forecast backtest MAPE, 9 tiers — 0.107–0.221" | `eval/evaluation_table.md` row 1, matches exactly (63 rows, 7 rolling origins) | TRUE | none |
| "Sense throughput — 3.83 s" | Same variance caveat as `technical` slide | TRUE (with noted variance) | none |
| "Pilot: not yet measured" / "Cost per play: not yet measured" | Matches `eval/evaluation_table.md` rows 9 and 13 exactly | TRUE | none |
| "9 of 13 §12 rows carry a real, committed measurement" | `eval/evaluation_table.md`'s own closing line says exactly this | TRUE | none |

## Slide `scale`

| Claim as written | What the code does | Verdict | Fix |
|---|---|---|---|
| "300 SKUs × 16 nodes senses in 3.83 s. Cloud Tasks fan-out ... are the extrapolation path" | Phrased as a stated path/plan, not a claim that Cloud Tasks fan-out is built — no Cloud Tasks code exists in the repo, and the deck doesn't claim there is any | TRUE (as phrased — aspirational language, correctly framed) | none |
| "A Cost Governor gates which gaps get a model call at all, by rupees at stake" | `agents/planner/governor.py` is real, implemented, and its decision is logged as a `cost_governor` trace event in `agents/planner/run.py` | TRUE | none |
| "A three-CSV ingestion contract ... is the path from a seeded demo tenant to a real retailer's own catalogue" | `docs/scale.md` documents this contract in detail. No CSV-parsing importer code exists (grepped `data/generator/`, `services/`, `jobs/` — none found). The deck's phrasing ("is the path") describes a documented contract, not a built importer, and does not claim otherwise. | TRUE (as phrased) | none |
| "**tenant_id** on every table, per-tenant policy text, **IAM scoped per service account** — not a single-demo hack" | `tenant_id`/policy: true, on every table. IAM: **false**. `infra/iam.sh` defines three least-privilege service accounts (`taal-agents`, `taal-sense`, `taal-web`), but `infra/deploy.sh` never passes `--service-account` to any `gcloud run deploy`/`gcloud run jobs deploy` call — grepped, zero matches. The actually-deployed services run under one shared, over-privileged default identity, not the scoped accounts the script defines. | **OVERCLAIM** | Reworded to describe the IAM matrix as written and ready, not applied to the live deployment |

## Slide `ux`

| Claim as written | What the code does | Verdict | Fix |
|---|---|---|---|
| Three screenshots (phone intake table, Play Desk, stylist chat) | Real Playwright-captured screenshots from `docs/screenshots/`, uploaded as deck assets, not mockups | TRUE | none |
| Persona job descriptions (Priya confirms low-confidence rows, Arjun reviews trace/guardrails, Meena gets grounded substitution) | Consistent with `agents/capture/vision.py`'s confirmation-question flow, the Play Desk trace panel, and `agents/customer/prompts/customer.md` | TRUE | none |
| "Judge mode: no login, a per-visitor sandbox ... LIVE/REPLAY badges" | Repeated from `summary`; verified | TRUE | none |

## Slide `close`

| Claim as written | What the code does | Verdict | Fix |
|---|---|---|---|
| "Real: Forecasts, gaps, estimator, guardrails, the Planner loop, holdout assignment, live re-forecast, chat, orders, measurement" | `README.md` itself lists "forecasts" as a real *code path* without qualification (it is real, running code — the caveat is about which product powers it, covered separately in README's "What is real, what is simulated"). But read alongside this deck's own `summary`/`technical` slides naming specific BigQuery products, an unqualified "Forecasts" here reads as endorsing that overclaim too. | **OVERCLAIM** (by adjacency, not in isolation) | Qualified to "Forecasts (local model; BigQuery SQL written and now verified against real data for one series)" |
| "Simulated, disclosed: the tenant Kutumb Mart ... no pilot has run yet" | Matches README exactly | TRUE | none |
| Live URL / repo link | Matches README | TRUE | none |
