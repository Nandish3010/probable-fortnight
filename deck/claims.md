# Deck claims

Every number on a slide has a row here, with the repo path (and line, where one is stable) that backs it.
`harness/checks/deck_claims.py` fails if a cited path or line does not exist. Slide text is in `deck/slides.html`.
Dates are the dates of the measurement, not of the deck.

| Slide | Claim | Source |
|---|---|---|
| 1 | Title block: Gemini 3.5 Flash plans in an ADK agent (guardrails price every rupee, holdout on every play); hero Rs 9,191 recovered vs doing nothing on one tea lot, projected | `config/models.toml:23`; `agents/planner/agent.py:29`; `eval/raw/tea_recorded_beat_2026-10-12.json:25-26` |
| 1 | Team: Nandish (lead), Rinu (co-builder) | `README.md:136-137` |
| 1 | FSSAI advisory, 3 Dec 2024, file RCD-13/1/2024-Regulatory-FSSAI(E-13150): minimum 30% shelf life or 45 days at delivery | `README.md:58`; `eval/raw/docs_truth_sweep_2026-09-27/fssai_citation.json` |
| 1 | Either-limit reading is Taal's configurable default | `README.md:58`; `config/tenant.demo.toml:6-18` |
| 2 | Sourced loss figure, as reported: Blinkit inventory losses about 1.8% of net order value (NOV), Inc42, 22 Jul 2026 (the Eternal letter it cites could not be opened, so the deck cites Inc42 only); NOV Rs 17,132 cr and 2,443 stores (same article); 17,132 / 2,443 x 4 x 1.8% = about Rs 0.5 cr per store per year; covers all inventory loss (expiry, shrinkage, damage, pilferage, transit) and annualises one quarter, so it is context for scale, not a Taal result. Source URL: https://inc42.com/buzz/blinkits-q1-adjusted-ebitda-rises-to-%e2%82%b9102-cr-others-losses-rise-on-nugget-rd/ | `docs/impact_numbers.md:22` |
| 2 | FSSAI advisory, 3 Dec 2024: 30% of shelf life or 45 days at delivery; advisory, not law; either-limit reading is Taal's configurable default | `README.md:58`; `eval/raw/docs_truth_sweep_2026-09-27/fssai_citation.json`; `config/tenant.demo.toml:6-18` |
| 2 | User: category or supply-chain head owns write-off and is the buyer; day to day a demand planner (Play Desk) and a dark-store manager (phone view) | `docs/impact_numbers.md:20`; `docs/impact_numbers.md:24`; `docs/DECISIONS.md:578-579`; `web/app/desk/page.tsx` |
| 2 | 3 of 7 practitioners write off weekly or daily | `eval/raw/feedback_summary_2026-10-09/summary.md:72-73` |
| 3 | Hero (projected, seeded tenant): Tea recovered vs doing nothing Rs 9,191 (waste avoided Rs 9,397 minus transfer cost Rs 206); beats a blanket 20% markdown by Rs 6,186; recorded Gemini run, 12 Oct 2026 | `eval/raw/tea_recorded_beat_2026-10-12.json:25-26`; `eval/raw/tea_recorded_beat_2026-10-12.json:40` |
| 3 | Holdout card big value +0.3 pp (pp glossed as percentage points; 95% CI glossed as confidence interval on the card); 95% CI -8.7 to +1.6; 1 of 355 treated responded, 0 of 39 held out; synthetic, inconclusive; Chips 323 / 29 (19 Sep) also inconclusive. Holdout, Tea: 355 treated (1 responder), 39 held out (0 responders), so +0.3 pp, 95% CI -8.7 to +1.6, inconclusive, synthetic orders, 12 Oct 2026 (one fast-forwarded order) | `eval/raw/tea_recorded_beat_2026-10-12.json:49-50`; `eval/raw/tea_recorded_beat_2026-10-12.json:85`; `eval/raw/tea_recorded_beat_2026-10-12.json:105`; `eval/raw/tea_recorded_beat_2026-10-12.json:99-102`; `docs/openapi.yaml` |
| 3 | Chips tile: 323 treated, 29 held out, +1.5 pp, 95% CI -12.4 to +5.6, inconclusive (synthetic) | `eval/raw/prior_update_2026-09-28.json:25-26`; `eval/raw/prior_update_2026-09-28.json:34-36` |
| 3 | Loop diagram (Forecast, Propose, Approve, Offer, Measure, priors update) | `docs/loop.svg` |
| 3 | Theme strip: nightly per-SKU, per-node forecasts with festival effects; human-approved offers | `README.md:54`; `jobs/sense/forecast.py:9` |
| 3 | 95% CI on the measured lift | `eval/raw/prior_update_2026-09-28.json:36-41` |
| 4 | Vendor cells (Blue Yonder, RELEX, Wasteless, Afresh, Flashfood) and the Unclear definition | `docs/vendors.md:17-22` |
| 4 | New line adds no number or competitor claim: the model proposes, code owns every rupee, every play keeps a holdout | `agents/gate/estimator.py:263`; `agents/gate/guardrails.py` |
| 4 | Taal row: Yes on sell-by cut-off, holdout, write-back | `docs/vendors.md:17`; `agents/gate/guardrails.py`; `services/api/approve.py` |
| 4 | Vendor pages read on 2026-10-09 | `docs/vendors.md:12` |
| 5 | Six gap types: Sense produces six (`README.md:54`); the `GapType` enum starts at line 35 and lists seven values, the seventh (`assortment_gap`) kept for schema compatibility only | `README.md:54`; `agents/gate/models.py:35-38` |
| 5 | LoopAgent, max 3 iterations | `agents/planner/agent.py:29` |
| 5 | Six deterministic planner tools | `agents/planner/tools.py:460` |
| 5 | Orders through an in-process MCP tool | `README.md:54` |
| 5 | 95% CI on Measure | `eval/raw/prior_update_2026-09-28.json:36-41` |
| 5 | Low-confidence rows must be confirmed | `agents/capture/vision.py:26` |
| 6 | Six steps, two loops (A: play into forecast; B: outcomes into priors) | `README.md:54`; `deck/slides.html:381-387` |
| 6 | Six gap types (Sense produces six; enum lists seven, see slide 5 row); eight guardrails | `README.md:54`; `agents/gate/models.py:35-38`; `agents/gate/models.py:44-46` |
| 7 | Play Desk frames, tea play recorded from Gemini, 12 Oct 2026, gemini-3.5-flash, 26.8 s, 1 attempt accepted (passed all guardrails), rationale cites 394 reachable customers; projected, seeded tenant. Economics frame: Rs 9,191 recovered vs doing nothing (waste avoided Rs 9,397 minus transfer cost Rs 206); Do nothing -Rs 35,020, Blanket markdown (20%) -Rs 32,015, This play -Rs 25,829; beats a blanket 20% markdown by Rs 6,186. Trace facts, recorded run_tea_ds04_v1_e6b5d8f9 (run_02, re-recorded trace, PR #98): 1 propose_play attempt, no rejection, 26.8 s (elapsed_ms 26791, wall 26.842 s), 394 customers after consent, model gemini-3.5-flash, 12 Oct 2026 (15:34 UTC), rationale Rs 9,191.29 and Rs 6,186.47 | `eval/raw/planner_real_traces_tea_2026-10-12c/run_02/result.json:11`; `eval/raw/planner_real_traces_tea_2026-10-12c/run_02/result.json:137`; `eval/raw/planner_real_traces_tea_2026-10-12c/run_02/result.json:134`; `eval/raw/planner_real_traces_tea_2026-10-12c/run_02/result.json:167`; `eval/raw/planner_real_traces_tea_2026-10-12c/run_02/result.json:172`; `eval/raw/planner_real_traces_tea_2026-10-12c/run_02/trace.jsonl:9`; `eval/raw/planner_real_traces_tea_2026-10-12c/summary.json:5`; `eval/raw/planner_real_traces_tea_2026-10-12c/summary.json:70`; `eval/raw/seed_pins.json:2`; `deck/img/tea-desk-economics.png`; `deck/img/tea-desk-trace.png`; `eval/raw/tea_recorded_beat_2026-10-12.json:25-26`; `eval/raw/tea_recorded_beat_2026-10-12.json:40` |
| 7 | Screenshot (customer chat with English gloss) | `deck/img/chat-gloss.png` |
| 8 | Scheduler 20:00 and 20:30 UTC | `infra/deploy.sh:331`; `infra/deploy.sh:361` |
| 8 | Nightly `taal-sense` job runs AI.FORECAST (TimesFM) into BigQuery | `infra/deploy.sh:309`; `jobs/sense/run.py:50-58` |
| 8 | Judge-facing path reads the frozen local snapshot and uses the local forecaster; nightly output is not read by it | `services/api/sandbox.py:45-51`; `infra/deploy.sh:294-298` |
| 8 | AI.FORECAST benchmarked, local won 45/45; caveat as in the file: a structural home-field advantage, seeded data generated with the same form the local model fits | `eval/raw/bigquery_ai_forecast_2026-09-27/head_to_head_summary.json:58` |
| 8 | Architecture boxes match the committed diagram | `docs/architecture.md:7-30`; `docs/architecture.svg` |
| 9 | Gemini 3.5 Flash (fallback 3.5 Flash-Lite) | `config/models.toml:23`; `eval/raw/model_verification_2026-10-10.json` |
| 9 | Service-to-decision table (planner proposes the play; Gemini drafts, chats, reads pallets; Approve attempts AI.GENERATE_TABLE for copy under a 3 s budget, usually templated; local forecaster re-forecasts on approve; Firestore feedback; Cloud Run serves and runs jobs; MCP tool places the order; guardrails and estimator own every rupee) | `agents/planner/agent.py:29`; `jobs/sense/copy.py:259`; `services/api/approve.py`; `agents/gate/estimator.py:263`; `docs/architecture.md:20` |
| 9 | LoopAgent max 3; 6 tools; 8 guardrails | `agents/planner/agent.py:29`; `agents/planner/tools.py:460`; `agents/gate/models.py:44-46` |
| 9 | AI.FORECAST benchmarked and run nightly; local forecaster served | `eval/raw/bigquery_ai_forecast_2026-09-27/head_to_head_summary.json`; `infra/deploy.sh:309` |
| 9 | Approve asks BigQuery AI.GENERATE_TABLE for the offer copy under a 3 s budget; if it misses, templated copy is used; the API reports which (copy.source) | `services/api/approve.py:33` (COPY_BUDGET_S), `:305-314` (copy_source set to existing, BigQuery result or templated), `:346` (response copy.source); `jobs/sense/copy.py:259`; `eval/raw/approve_live_split_2026-10-12.json` |
| 9 | GitHub Actions runs verify, then deploys to Cloud Run on every merge to main | `.github/workflows/verify.yml:68-98` |
| 10 | ₹486 / $5.86 per 30 days, modelled from measured usage | `eval/raw/cost_measurement_2026-09-23.json:309-310` |
| 10 | The 486 rupee figure was measured on 23 Sep on gemini-2.5-flash-family pricing, before the 10 Oct switch to gemini-3.5-flash; not re-measured | `eval/raw/cost_measurement_2026-09-23.json`; `config/models.toml:17` |
| 10 | The 486 rupee measurement window had 0 plays and 0 gaps (idle-plus-nightly cost; no cost per play) | `eval/raw/cost_measurement_2026-09-23.json:312-313` |
| 10 | 752 BigQuery jobs | `eval/raw/cost_measurement_2026-09-23.json:284` |
| 10 | Micro ₹200-500 (1 shop, 500 SKUs); Mid ₹2,500-5,000 (300 SKUs, 10 nodes); Large ₹1-2 lakh (20,000 SKUs, 500 nodes); all estimates | `docs/scale.md:83-85` |
| 10 | Buyer is the category or supply-chain head; basis per node per month or % of rupees rescued | `docs/impact_numbers.md:20`; `docs/impact_numbers.md:24`; `docs/DECISIONS.md:578-579` |
| 10 | Projected margin less run cost illustration (not a break-even; no fee is set): ₹347,356 per 28-day run at the 5% prior / 16 nodes (10 dark stores + 6 outlets) ≈ ₹21,710 per node; less the Mid profile cost ₹2,500 to 5,000 a month / 16 = ₹156 to ₹313 per node (the measured ₹486 / 16 ≈ ₹30 had zero plays in its window) | `README.md:68`; `docs/impact_numbers.md:26`; `eval/raw/portfolio_2026-09-24.json`; `docs/scale.md:83-85`; `eval/raw/cost_measurement_2026-09-23.json:312` |
| 10 | 16 nodes (10 dark stores, 6 outlets) | `eval/raw/docs_truth_sweep_2026-09-27/tenant_counts.json:21` |
| 11 | Caption: outcomes on a fast-forwarded day, synthetic orders. Outcomes screenshot after Fast-forward (sandbox, 12 Oct): Tea, 355 offered, 39 held out, 1 of 355 vs 0 of 39 ordered, +0.3 pp, 95% CI -8.7 to +1.6, inconclusive, SYNTHETIC | `deck/img/outcomes.png`; `eval/raw/tea_recorded_beat_2026-10-12.json:49-50`; `eval/raw/tea_recorded_beat_2026-10-12.json:85`; `eval/raw/tea_recorded_beat_2026-10-12.json:105` |
| 11 | 70% confidence threshold for the confirm step | `agents/capture/vision.py:26` |
| 11 | Screenshots (phone confirm step, Outcomes with SYNTHETIC badge) | `deck/img/phone-confirm.png`; `deck/img/outcomes.png` |
| 12 | Header: measured and dated, each card names its source file; Approve card labelled "curl, 6 calls" (method field: curl, one POST per sample) | `eval/raw/approve_timing_2026-10-12b.json` |
| 12 | Planner live 5/5 proposed, 0 fallbacks, 21.8 to 27.6 s (10 Oct, chips, gemini-3.5-flash); Tea 8/8 proposed, 0 fallbacks, 19.0 to 31.4 s wall (12 Oct, re-recorded; 7 of 8 passed on the first attempt) | `eval/raw/planner_real_traces_2026-10-10/summary.json`; `eval/raw/planner_real_traces_tea_2026-10-12c/summary.json` |
| 12 | Live plan, deployed, 11 Oct, gemini-3.5-flash: 22 of 24 model-planned (92% pass rate), 0 fallbacks, planner elapsed p50 26.5 s and p95 31.8 s over the 22 observed runs, 1 loop iteration each, 90 s deadline; 2 runs unobservable (poll 404 on a cold instance) counted as not passed | `eval/raw/plan_live_2026-10-12.json` |
| 12 | ADK eval first-attempt acceptance: first proposed play passed the gate 41/46 on gemini-3.5-flash (12 Oct) vs 5/46 on gemini-2.5-flash (9 Oct) | `eval/raw/live_eval_2026-10-12/first_attempt.json:10-14` (live_2026-10-09), `:17-23` (live_2026-10-12) |
| 12 | Earlier 3-run check, 10 Oct: server elapsed 30.3 / 27.5 / 29.6 s, 3 of 3 model-planned | `eval/raw/live_replan_timing_2026-10-10.json` |
| 12 | Before the fix, 9 Oct: 47.7 / 47.7 / 30.8 s, 2 of 3 fell back to rules at a 45 s deadline | `eval/raw/live_replan_timing_2026-10-09.json`; `eval/raw/planner_live_rerun_2026-10-09/summary.json` |
| 12 | Customer agent p50 4.56 s, p95 6.48 s, 50/50 returned 200 (28 Sep, gemini-2.5-flash); 6 s budget | `eval/raw/customer_latency_2026-09-28/analysis.json:5-8`; `docs/architecture.md:108` |
| 12 | Approve + re-forecast, 12 Oct, curl after #90: about 3 to 7 s warm (Tea 4.0, 6.8, 3.3, 3.3 s; chips 3.3, 3.3 s; first call after idle takes longer). Before #90 (history): recorded plays 7 to 15 s, scripted 6 to 7 s. Before that, 8.3 s (21 Sep) and 10.6 s (28 Sep), write-off ₹9,194 to ₹8,068 | `eval/raw/approve_timing_2026-10-12b.json`; `eval/raw/approve_timing_2026-10-12.json` (history); `eval/raw/sweep_vertex_2026-09-21.txt:12`; `eval/raw/post_deploy_check_2026-09-28/summary.json:30-39` |
| 12 | Agent simulation 190/190 (21 Sep, gemini-2.5-flash) | `eval/raw/agent_simulation_2026-09-21.json:6-7` |
| 12 | Vision 30/30 correct dates, synthetic photos (21 Sep, gemini-2.5-flash) | `eval/raw/vision_synthetic_2026-09-21.json`; `eval/evaluation_table.md` |
| 12 | Forecast backtest, synthetic: WAPE 0.113, MAPE 0.133, 63 rows (20 Sep) | `eval/raw/external_backtest_2026-10-09.json:120-123`; `eval/raw/backtest_rows_2026-09-20.jsonl` |
| 12 | Public non-grocery dataset backtest WAPE 0.83 | `eval/raw/external_backtest_2026-10-09.json:77`; `eval/external_backtest.md` |
| 12 | Live eval 2026-10-12, gemini-3.5-flash: rationale judge 15/15 (same-family judge), ADK response match 43/46 (93%), exact trajectory 1/46 (28 Sep recordings contain propose_play retries; gemini-3.5-flash proposes first time in 40 of 45 cases); prompt v6, v7 not measured; 9 Oct on gemini-2.5-flash was 15/15, 38/46, 6/46 | `eval/raw/live_eval_2026-10-12/summary.json:9,10,19,20,24` (40 of 45 at line 24); `eval/raw/live_eval_2026-10-12/adk_vertex/scores.json`; `eval/raw/live_eval_2026-10-12/rationale_judge.json`; `eval/raw/live_eval_2026-10-09/summary.json:5` |
| 12 | Tests: 470+ pytest test functions (`grep -rc "def test_" tests`) and 490+ Playwright `test(` cases in web/tests (473 e2e + 25 live) run in make verify; 24 live-stack cases in web/tests/live run in a second CI job; CI gate is make verify in verify.yml on every pull request and push to main | `tests`; `web/tests/e2e`; `web/tests/live`; `.github/workflows/verify.yml:1-24`; `Makefile:16` |
| 12 | Latency story: live plan p50 26.5 s and p95 31.8 s (22/24, 11 Oct); Approve about 3 to 7 s (measured 12 Oct after #90; first call after idle takes longer); recorded runs 21.8 to 27.6 s (10 Oct chips) and 19.0 to 31.4 s (12 Oct Tea, 8 runs); the Plan live chip reads /health plan_live_eval | `eval/raw/plan_live_2026-10-12.json`; `eval/raw/approve_timing_2026-10-12b.json`; `services/api/plan_live_eval.py` |
| 13 | 7 usable responses; 10 collected, 3 excluded as flagged | `eval/raw/feedback_summary_2026-10-09/summary.md:7-9`; `config/feedback_exclusions.json` |
| 13 | 3 of 7 write off weekly or daily (2 weekly, 1 daily) | `eval/raw/feedback_summary_2026-10-09/summary.md:72-73` |
| 13 | 3 of 6 online sellers say the sell-by rule limits what they sell | `eval/raw/feedback_summary_2026-10-09/summary.md:125`; `eval/raw/feedback_summary_2026-10-09/summary.md:60` |
| 13 | 0 of 7 measure against a control group | `eval/raw/feedback_summary_2026-10-09/summary.md:136` |
| 13 | 4 of 7 want a one-week pilot | `eval/raw/feedback_summary_2026-10-09/summary.md:232` |
| 13 | Quotes, role and business type | `eval/raw/feedback_summary_2026-10-09/summary.json:11356`; `eval/raw/feedback_summary_2026-10-09/summary.json:11370` |
| 14 | Persona steps: Desk, phone, chat | `web/app/desk/page.tsx`; `README.md:25-31`; `web/components/ChatPanel.tsx:28` |
| 14 | Phone view: rows below 0.7 confidence are confirmed | `agents/capture/vision.py:26` |
| 14 | STOP withdraws consent | `docs/privacy.md:56-64` |
| 14 | Badge meanings (LIVE, REPLAY, SYNTHETIC, Recorded from Gemini) | `web/components/Badge.tsx`; `README.md:88` |
| 15 | Tea: recovered vs doing nothing Rs 9,191 (projected, seeded tenant); 103 units, ₹35,020 at stake; play net -₹25,829 vs -₹32,015 blanket markdown; ahead by ₹6,186 | `eval/raw/tea_recorded_beat_2026-10-12.json:43-44`; `agents/gate/estimator.py:263` |
| 15 | Chips (10 Oct, API snapshot; projected): 368 units, ₹9,200 at stake; play net -₹8,468 vs -₹8,189 blanket markdown; behind by ₹279 | `eval/raw/tea_beat_api_2026-10-10.json:25-30`; `docs/impact_math.md:21` |
| 15 | Prior sensitivity, margin 2% / 5% / 10%: ₹1.41 / 3.47 / 6.19 lakh | `eval/raw/portfolio_prior_sensitivity_2026-10-09.json` |
| 15 | Prior sensitivity, waste avoided 2% / 5% / 10%: ₹3.26 / 7.06 / 11.18 lakh | `eval/raw/portfolio_prior_sensitivity_2026-10-09.json` |
| 15 | 550 grocery gaps; plays planned at each prior: 421 (2%), 424 (5%), 423 (10%) (planned.count in runs 2pct, 5pct, 10pct) | `eval/raw/portfolio_prior_sensitivity_2026-10-09.json` |
| 15 | Synthetic holdout, Chips (19 Sep): 323 treated, 29 held back, lift +1.5 points, 95% CI -12.4 to +5.6 | `eval/raw/prior_update_2026-09-28.json:25-36` |
| 15 | Synthetic holdout, Tea: 355 treated, 39 held back; 1 responder vs 0, inconclusive | `eval/raw/tea_recorded_beat_2026-10-12.json:49-50`; `eval/raw/tea_recorded_beat_2026-10-12.json:85`; `eval/raw/tea_recorded_beat_2026-10-12.json:105` |
| 15 | Projected at 5%: ₹347,356 margin, ₹706,183 waste avoided | `eval/raw/portfolio_prior_sensitivity_2026-10-09.json`; `docs/impact_math.md` |
| 15 | Measured on real customers: none yet | `docs/pilot.md:19-20` |
| 15 | 7 usable responses; 3 of 7 write off weekly or daily | `eval/raw/feedback_summary_2026-10-09/summary.md:7-9`; `eval/raw/feedback_summary_2026-10-09/summary.md:72-73` |
| 16 | Today: services run as owner-role deploy identity; CI uses a stored key; secrets in managed store. Next: least-privilege service accounts and workload identity | `infra/README.md:94-109` (owner role, deviation not yet corrected); `.github/workflows/verify.yml:93-95` (stored key credentials_json); `infra/README.md:225-227`; `infra/README.md:239-241` (Secret Manager) |
| 16 | Models pinned (gemini-3.5-flash, Flash-Lite fallback); gemini-2.5-flash retires 20 Oct 2026 | `config/models.toml:23`; `docs/DECISIONS.md:52` |
| 16 | Measured: Sense 3.8 s (local, 300 SKUs), chat p50 4.56 s, p95 6.48 s (50 calls, 28 Sep, gemini-2.5-flash; same as slide 12); live plan p50 26.5 s and p95 31.8 s (22/24, 11 Oct); Approve about 3 to 7 s (measured 12 Oct after #90; first call after idle takes longer) | `docs/scale.md:11`; `eval/raw/customer_latency_2026-09-28/analysis.json:5-8`; `eval/raw/plan_live_2026-10-12.json`; `eval/raw/approve_timing_2026-10-12b.json` |
| 16 | Estimate: 20,000 SKUs, 500 nodes; breaks first: max-instances 1 with re-plan state in process memory, then the planner queue | `docs/scale.md:37-38`; `docs/scale.md:95-97`; `infra/deploy.sh:239` |
| 16 | Buyer, fee basis, pilot 50 to 60 testers one week, run cost ₹486 (usage measured 23 Sep on gemini-2.5-flash) | `docs/impact_numbers.md:24`; `docs/pilot.md:19-20`; `eval/raw/cost_measurement_2026-09-23.json:309-310` |
| 16 | Profile estimates: ₹200-500, ₹2,500-5,000, ₹1-2 lakh | `docs/scale.md:83-85` |
| 17 | Pilot: 50-60 consented testers, one week, 40-50% holdout, metric pre-registered | `docs/pilot.md:19-20` |
| 17 | Vision 30/30 correct dates on synthetic photos (21 Sep, gemini-2.5-flash) | `eval/raw/vision_synthetic_2026-09-21.json` |
| 17 | Vision harness built; synthetic photos only so far | `eval/evaluation_table.md`; `Makefile` |
| 17 | BigQuery path built, flag off | `docs/scale.md:40-47`; `infra/deploy.sh:294` |
| 18 | Repo and live app URLs | `README.md:17`; `README.md:27` |
| 18 | Recap: Rs 9,191 recovered vs doing nothing, projected, seeded tenant; 22 of 24 live plans on gemini-3.5-flash, p50 26.5 s (11 Oct); holdout synthetic and inconclusive | `eval/raw/tea_recorded_beat_2026-10-12.json:25-26`; `eval/raw/plan_live_2026-10-12.json` |
