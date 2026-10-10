# Deck claims

Every number on a slide has a row here, with the repo path (and line, where one is stable) that backs it.
`harness/checks/deck_claims.py` fails if a cited path or line does not exist. Slide text is in `deck/slides.html`.
Dates are the dates of the measurement, not of the deck.

| Slide | Claim | Source |
|---|---|---|
| 1 | Team: Nandish (lead), Rinu (co-builder) | `README.md:34-35` |
| 1 | FSSAI advisory, 3 Dec 2024, file RCD-13/1/2024-Regulatory-FSSAI(E-13150): minimum 30% shelf life or 45 days at delivery | `README.md:78-83`; `eval/raw/docs_truth_sweep_2026-09-27/fssai_citation.json` |
| 1 | Either-limit reading is Taal's configurable default | `README.md:83-89`; `config/tenant.demo.toml:6` |
| 2 | 6 days to the online sell-by cut-off | `eval/raw/flagship_facts_2026-09-27.json:34` |
| 2 | 368 units | `eval/raw/flagship_facts_2026-09-27.json:14` |
| 2 | ₹9,200 at stake | `eval/raw/flagship_facts_2026-09-27.json:19` |
| 2 | Recorded Gemini run, 10 Oct; one schema rejection, then all eight guardrails pass | `eval/raw/planner_real_traces_2026-10-10/summary.json`; `eval/raw/planner_real_traces_2026-10-10/run_05/play.json`; `README.md:92-125` |
| 2 | Approve assigns 323 treated, 29 holdout | `eval/raw/prior_update_2026-09-28.json:25-26`; `README.md:92-125` |
| 2 | Theme strip: nightly per-SKU, per-node forecasts with festival effects; human-approved offers | `docs/DECISIONS.md:81`; `jobs/sense/forecast.py:9` |
| 2 | 95% CI on the measured lift | `eval/raw/prior_update_2026-09-28.json:36-41` |
| 3 | Vendor cells (Blue Yonder, RELEX, Wasteless, Afresh, Flashfood) and the Unclear definition | `README.md:194-218` |
| 3 | Taal row: Yes on sell-by cut-off, holdout, write-back | `README.md:201`; `agents/gate/guardrails.py`; `services/api/approve.py` |
| 3 | Vendor pages read on 2026-10-09 | `README.md:194-198` |
| 4 | Six gap types | `README.md:227`; `agents/gate/models.py:36-38` |
| 4 | LoopAgent, max 3 iterations | `agents/planner/agent.py:28` |
| 4 | Six deterministic planner tools | `agents/planner/tools.py:406` |
| 4 | Orders through an in-process MCP tool | `README.md:230` |
| 4 | 95% CI on Measure | `eval/raw/prior_update_2026-09-28.json:36-41` |
| 4 | Low-confidence rows must be confirmed | `agents/capture/vision.py:25` |
| 5 | Six steps, two loops (A: play into forecast; B: outcomes into priors) | `README.md:220-232` |
| 5 | Six gap types; eight guardrails | `README.md:227-228`; `agents/gate/models.py:44-46` |
| 6 | Four proposals, three rejected by cite-or-drop, fourth passes all eight guardrails | `eval/raw/planner_real_traces_2026-09-28/run_04/result.json`; `README.md:92-125` |
| 6 | The trace screenshot is the 28 Sep run (before the tokenizer fix); the 10 Oct run needed one schema retry | `eval/raw/planner_real_traces_2026-10-10/summary.json` |
| 6 | Screenshots (Play Desk trace, customer chat with English gloss) | `deck/img/trace-attempts.png`; `deck/img/chat-gloss.png` |
| 7 | Scheduler 20:00 and 20:30 UTC | `infra/deploy.sh:320`; `infra/deploy.sh:350` |
| 7 | Nightly `taal-sense` job runs AI.FORECAST (TimesFM) into BigQuery | `infra/deploy.sh:309`; `jobs/sense/run.py:50-58` |
| 7 | Judge-facing path reads the frozen local snapshot and uses the local forecaster; nightly output is not read by it | `services/api/sandbox.py:45-51`; `infra/deploy.sh:294-298` |
| 7 | AI.FORECAST benchmarked, local won 45/45 | `eval/raw/bigquery_ai_forecast_2026-09-27/head_to_head_summary.json:58` |
| 7 | Architecture boxes match the committed diagram | `docs/architecture.md:7-30`; `docs/architecture.svg` |
| 8 | Gemini 3.5 Flash (fallback 3.5 Flash-Lite) | `config/models.toml:23`; `eval/raw/model_verification_2026-10-10.json` |
| 8 | LoopAgent max 3; 6 tools; 8 guardrails | `agents/planner/agent.py:28`; `agents/planner/tools.py:406`; `agents/gate/models.py:44-46` |
| 8 | AI.FORECAST benchmarked and run nightly; local forecaster served | `eval/raw/bigquery_ai_forecast_2026-09-27/head_to_head_summary.json`; `infra/deploy.sh:309` |
| 8 | AI.GENERATE_TABLE writes offer copy at approve (vertex backend) | `jobs/sense/copy.py:95`; `docs/architecture.md:20` |
| 8 | GitHub Actions runs verify, then deploys to Cloud Run on every merge to main | `.github/workflows/verify.yml:68-98` |
| 9 | ₹486 / $5.86 per 30 days, modelled from measured usage | `eval/raw/cost_measurement_2026-09-23.json:309-310` |
| 9 | 752 BigQuery jobs | `eval/raw/cost_measurement_2026-09-23.json:284` |
| 9 | Micro ₹200-500 (1 shop, 500 SKUs); Mid ₹2,500-5,000 (300 SKUs, 10 nodes); Large ₹1-2 lakh (20,000 SKUs, 500 nodes); all estimates | `docs/scale.md:83-85` |
| 9 | Buyer is the category or supply-chain head; basis per node per month or % of rupees rescued | `README.md:55`; `docs/DECISIONS.md:554` |
| 9 | Break-even illustration: ₹347,356 / 16 nodes ≈ ₹21,710, ₹486 / 16 ≈ ₹30 per node per month | `README.md:57`; `eval/raw/portfolio_2026-09-24.json` |
| 9 | 16 nodes (10 dark stores, 6 outlets) | `eval/raw/docs_truth_sweep_2026-09-27/tenant_counts.json:21` |
| 10 | Screenshot shows the 28 Sep build, 316 / 36; the current seeded example is 323 treated, 29 holdout | `eval/raw/prior_update_2026-09-28.json:25-26` |
| 10 | 70% confidence threshold for the confirm step | `agents/capture/vision.py:25` |
| 10 | Screenshots (phone confirm step, Outcomes with SYNTHETIC badge) | `deck/img/phone-confirm.png`; `deck/img/outcomes.png` |
| 11 | Planner live 5/5 proposed, 0 fallbacks, 21.8 to 27.6 s (10 Oct) | `eval/raw/planner_real_traces_2026-10-10/summary.json` |
| 11 | Live re-plan, deployed, 10 Oct: server elapsed 30.3 / 27.5 / 29.6 s, 3 of 3 model-planned, 0 fallbacks, 1 loop iteration each, 90 s deadline | `eval/raw/live_replan_timing_2026-10-10.json` |
| 11 | Before the fix, 9 Oct: 47.7 / 47.7 / 30.8 s, 2 of 3 fell back to rules at a 45 s deadline | `eval/raw/live_replan_timing_2026-10-09.json`; `eval/raw/planner_live_rerun_2026-10-09/summary.json` |
| 11 | Customer agent p50 4.56 s, p95 6.48 s, 50/50 returned 200 (28 Sep); 6 s budget | `eval/raw/customer_latency_2026-09-28/analysis.json:5-8`; `docs/architecture.md:108` |
| 11 | Approve + re-forecast 8.3 s (21 Sep) and 10.6 s (28 Sep); write-off ₹9,194 to ₹8,068 | `eval/raw/sweep_vertex_2026-09-21.txt:12`; `eval/raw/post_deploy_check_2026-09-28/summary.json:30-39` |
| 11 | Agent simulation 190/190 (21 Sep) | `eval/raw/agent_simulation_2026-09-21.json:6-7` |
| 11 | Vision 30/30 correct dates, synthetic photos (21 Sep) | `eval/raw/vision_synthetic_2026-09-21.json`; `eval/evaluation_table.md` |
| 11 | Forecast backtest, synthetic: WAPE 0.113, MAPE 0.133, 63 rows (20 Sep) | `eval/raw/external_backtest_2026-10-09.json:120-123`; `eval/raw/backtest_rows_2026-09-20.jsonl` |
| 11 | Public non-grocery dataset backtest WAPE 0.83 | `eval/raw/external_backtest_2026-10-09.json:77`; `eval/external_backtest.md` |
| 11 | Live eval 2026-10-09: rationale judge 15/15 (same-family judge), ADK response match 38/46, exact trajectory 6/46 | `eval/raw/live_eval_2026-10-09/summary.json:5` |
| 12 | 7 usable responses; 10 collected, 3 excluded as flagged | `eval/raw/feedback_summary_2026-10-09/summary.md:7-9`; `config/feedback_exclusions.json` |
| 12 | 3 of 7 write off weekly or daily (2 weekly, 1 daily) | `eval/raw/feedback_summary_2026-10-09/summary.md:72-73` |
| 12 | 3 of 6 online sellers say the sell-by rule limits what they sell | `eval/raw/feedback_summary_2026-10-09/summary.md:125`; `eval/raw/feedback_summary_2026-10-09/summary.md:60` |
| 12 | 0 of 7 measure against a control group | `eval/raw/feedback_summary_2026-10-09/summary.md:136` |
| 12 | 4 of 7 want a one-week pilot | `eval/raw/feedback_summary_2026-10-09/summary.md:232` |
| 12 | Quotes, role and business type | `eval/raw/feedback_summary_2026-10-09/summary.json:11356`; `eval/raw/feedback_summary_2026-10-09/summary.json:11370` |
| 13 | Persona steps: Desk, phone, chat | `web/app/desk/page.tsx`; `README.md:11-13`; `web/components/ChatPanel.tsx:28` |
| 13 | Phone view: rows below 0.7 confidence are confirmed | `agents/capture/vision.py:25` |
| 13 | STOP withdraws consent | `docs/privacy.md:56-64` |
| 13 | Badge meanings (LIVE, REPLAY, SYNTHETIC, Recorded from Gemini) | `web/components/Badge.tsx`; `README.md:15` |
| 14 | Tea: 103 units, ₹35,020 at stake; play net -₹27,522 vs -₹32,015 blanket markdown; ahead by ₹4,493 | `eval/raw/tea_beat_api_2026-10-10.json`; `agents/gate/estimator.py:263` |
| 14 | Chips: 368 units, ₹9,200 at stake; play net -₹8,468 vs -₹8,189; behind by ₹279 | `eval/raw/planner_real_traces_2026-10-10/run_05/play.json`; `eval/raw/tea_beat_api_2026-10-10.json` |
| 14 | Prior sensitivity, margin 2% / 5% / 10%: ₹1.41 / 3.47 / 6.19 lakh | `eval/raw/portfolio_prior_sensitivity_2026-10-09.json` |
| 14 | Prior sensitivity, waste avoided 2% / 5% / 10%: ₹3.26 / 7.06 / 11.18 lakh | `eval/raw/portfolio_prior_sensitivity_2026-10-09.json` |
| 14 | 550 grocery gaps; 421 / 424 / 423 plays planned at 2% / 5% / 10% | `eval/raw/portfolio_prior_sensitivity_2026-10-09.json` |
| 14 | Synthetic holdout: 323 treated, 29 held back, lift +1.5 points, 95% CI -12.4 to +5.6 | `eval/raw/prior_update_2026-09-28.json:25-36` |
| 14 | Projected at 5%: ₹347,356 margin, ₹706,183 waste avoided | `eval/raw/portfolio_prior_sensitivity_2026-10-09.json`; `docs/impact_math.md` |
| 14 | Measured on real customers: none yet | `docs/pilot.md:19-20` |
| 14 | 7 usable responses; 3 of 7 write off weekly or daily | `eval/raw/feedback_summary_2026-10-09/summary.md:7-9`; `eval/raw/feedback_summary_2026-10-09/summary.md:72-73` |
| 15 | Least-privilege accounts, stored CI key, managed secrets | `infra/README.md:101-108`; `.github/workflows/verify.yml:94`; `infra/README.md:193-194` |
| 15 | Models pinned (gemini-3.5-flash, Flash-Lite fallback); gemini-2.5-flash retires 20 Oct 2026 | `config/models.toml:23`; `docs/DECISIONS.md:207` |
| 15 | Measured: Sense 3.8 s, chat 4.5 to 6.9 s; planner re-plan 27.5 to 30.3 s live | `docs/scale.md:11-14`; `eval/raw/live_replan_timing_2026-10-10.json` |
| 15 | Estimate: 20,000 SKUs, 500 nodes; breaks first: planner queue | `docs/scale.md:37-38`; `docs/scale.md:95-97` |
| 15 | Buyer, fee basis, pilot 50 to 60 testers one week, run cost ₹486 | `README.md:55`; `docs/pilot.md:19-20`; `eval/raw/cost_measurement_2026-09-23.json:309-310` |
| 15 | Profile estimates: ₹200-500, ₹2,500-5,000, ₹1-2 lakh | `docs/scale.md:83-85` |
| 16 | Pilot: 50-60 consented testers, one week, 40-50% holdout, metric pre-registered | `docs/pilot.md:19-20` |
| 16 | Vision harness built; synthetic photos only so far | `eval/evaluation_table.md`; `Makefile` |
| 16 | BigQuery path built, flag off | `docs/scale.md:40-47`; `infra/deploy.sh:294` |
| 17 | Repo and live app URLs | `README.md:9`; `README.md:1` |
