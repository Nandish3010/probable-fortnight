# Deck claims

Every number on a slide has a row here, with the repo path (and line, where one is stable) that backs it.
`harness/checks/deck_claims.py` fails if a cited path or line does not exist. Slide text is in `deck/slides.html`.
Dates are the dates of the measurement, not of the deck.

| Slide | Claim | Source |
|---|---|---|
| 1 | Team: Nandish (lead), Rinu (co-builder) | `README.md:23-24` |
| 1 | FSSAI advisory, 3 Dec 2024, file RCD-13/1/2024-Regulatory-FSSAI(E-13150): minimum 30% shelf life or 45 days at delivery | `README.md:67-72`; `eval/raw/docs_truth_sweep_2026-09-27/fssai_citation.json` |
| 1 | Either-limit reading is Taal's configurable default | `README.md:72-78`; `config/tenant.demo.toml:6` |
| 2 | 6 days to the online sell-by cut-off | `eval/raw/flagship_facts_2026-09-27.json:34` |
| 2 | 368 units | `eval/raw/flagship_facts_2026-09-27.json:14` |
| 2 | ₹9,200 at stake | `eval/raw/flagship_facts_2026-09-27.json:19` |
| 2 | Recorded Gemini run, 28 Sep; rationale rejected 3 times by cite-or-drop, passed on the 4th | `eval/raw/planner_real_traces_2026-09-28/summary.json`; `README.md:81-95` |
| 2 | Approve assigns 316 treated, 36 holdout | `eval/raw/prior_update_2026-09-28.json:25-26`; `README.md:13` |
| 2 | 95% CI on the measured lift | `eval/raw/prior_update_2026-09-28.json:36-41` |
| 3 | Vendor cells (Blue Yonder, RELEX, Wasteless, Afresh, Flashfood) and the Unclear definition | `README.md:172-196` |
| 3 | Taal row: Yes on sell-by cut-off, holdout, write-back | `README.md:179`; `agents/gate/guardrails.py`; `services/api/approve.py` |
| 3 | Vendor pages read on 2026-10-09 | `README.md:172-176` |
| 4 | Six gap types | `README.md:205`; `agents/gate/models.py:36-38` |
| 4 | LoopAgent, max 3 iterations | `agents/planner/agent.py:28` |
| 4 | Six deterministic planner tools | `agents/planner/tools.py:402` |
| 4 | Orders through an in-process MCP tool | `README.md:208` |
| 4 | 95% CI on Measure | `eval/raw/prior_update_2026-09-28.json:36-41` |
| 4 | Low-confidence rows must be confirmed | `agents/capture/vision.py:25` |
| 5 | Six steps, two loops (A: play into forecast; B: outcomes into priors) | `README.md:198-210` |
| 5 | Six gap types; eight guardrails | `README.md:205-206`; `agents/gate/models.py:44-46` |
| 6 | Four proposals, three rejected by cite-or-drop, fourth passes all eight guardrails | `eval/raw/planner_real_traces_2026-09-28/run_04/result.json`; `README.md:81-95` |
| 6 | Screenshots (Play Desk trace, customer chat with English gloss) | `deck/img/trace-attempts.png`; `deck/img/chat-gloss.png` |
| 7 | Scheduler 20:00 and 20:30 UTC | `infra/deploy.sh:320`; `infra/deploy.sh:350` |
| 7 | AI.FORECAST benchmarked, local won 45/45 | `eval/raw/bigquery_ai_forecast_2026-09-27/head_to_head_summary.json:58` |
| 7 | Architecture boxes match the committed diagram | `docs/architecture.md:7-30`; `docs/architecture.svg` |
| 8 | Gemini 2.5 Flash | `config/models.toml:23` |
| 8 | LoopAgent max 3; 6 tools; 8 guardrails | `agents/planner/agent.py:28`; `agents/planner/tools.py:402`; `agents/gate/models.py:44-46` |
| 8 | AI.FORECAST and ARIMA_PLUS_XREG benchmarked; local forecaster served | `eval/raw/bigquery_ai_forecast_2026-09-27/head_to_head_summary.json`; `eval/raw/bigquery_arima_xreg_forecast_2026-09-23.json` |
| 8 | GitHub Actions runs verify, then deploys to Cloud Run on every merge to main | `.github/workflows/verify.yml:68-98` |
| 9 | ₹486 / $5.86 per 30 days, modelled from measured usage | `eval/raw/cost_measurement_2026-09-23.json:309-310` |
| 9 | 752 BigQuery jobs | `eval/raw/cost_measurement_2026-09-23.json:284` |
| 9 | Micro ₹200-500 (1 shop, 500 SKUs); Mid ₹2,500-5,000 (300 SKUs, 10 nodes); Large ₹1-2 lakh (20,000 SKUs, 500 nodes); all estimates | `docs/scale.md:83-85` |
| 9 | Buyer is the category or supply-chain head; basis per node per month or % of rupees rescued | `README.md:44`; `docs/DECISIONS.md:554` |
| 9 | Break-even illustration: ₹347,356 / 16 nodes ≈ ₹21,710, ₹486 / 16 ≈ ₹30 per node per month | `README.md:46`; `eval/raw/portfolio_2026-09-24.json` |
| 9 | 16 nodes (10 dark stores, 6 outlets) | `eval/raw/docs_truth_sweep_2026-09-27/tenant_counts.json:21` |
| 10 | 316 treated, 36 holdout on the Outcomes screen | `eval/raw/prior_update_2026-09-28.json:25-26` |
| 10 | 70% confidence threshold for the confirm step | `agents/capture/vision.py:25` |
| 10 | Screenshots (phone confirm step, Outcomes with SYNTHETIC badge) | `deck/img/phone-confirm.png`; `deck/img/outcomes.png` |
| 11 | Planner live 5/5 proposed, 0 fallbacks, 34-65 s (28 Sep) | `eval/raw/planner_real_traces_2026-09-28/summary.json:126`; `eval/raw/planner_real_traces_2026-09-28/summary.json:183` |
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
| 13 | Pilot: 50-60 consented testers, one week, 40-50% holdout, metric pre-registered | `docs/pilot.md:19-20` |
| 13 | Vision harness built; synthetic photos only so far | `eval/evaluation_table.md`; `Makefile` |
| 13 | BigQuery path built, flag off | `docs/scale.md:40-47`; `infra/deploy.sh:294` |
| 14 | Repo and live app URLs | `README.md:12`; `README.md:1` |
