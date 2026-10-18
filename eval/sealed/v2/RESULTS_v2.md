## Sealed eval v2 and markdown option (19 Oct 2026)

Label: measured. Model `gemini-3.5-flash`, prompt v8, asia-south1. Recovery is the projected recovery under Taal's own estimator (versus doing nothing) on a synthetic tenant. A fallback play or no play counts as not beating any baseline. Protocol: `eval/sealed/PROTOCOL_v2.md`. Raw files: `eval/raw/sealed_v2_2026-10-19/`, `eval/raw/sealed_v1_regression_2026-10-19/` and `..._cont/`, and v1 in `eval/raw/sealed_2026-10-19/`.

### What changed in code (commit 14bcb7c)

* A `markdown` mechanic: a price cut at 10, 20 or 35% on the online node, with a holdout rule for price cuts, and the scenarios are scored on a price cut with a node holdout or none.
* One demand model (`units_sold_at_discount`, per-category elasticity, default 1.0) now prices both plays and the counterfactuals, including the blanket 20% baseline.
* A `beats_markdown` gate check: a proposed play must beat the best allowed markdown within a tolerance of max(₹500, 5% of the best markdown's recovery).
* Planner prompt v8 (`planner.md` sha256 `f9f67cfb...ce13895`), which names the markdown option.
* Tenant config `[markdown]` (depths 10/20/35, clearance exception off) and the v2 scenario generator `eval/sealed/make_scenarios_v2.py`.

### Method

* New seed 71903482, in no tracked file before the scenario file was written; 36 scenarios: 29 feature stratum (v1's gap type x lot band x deadline band cells) plus 7 markdown stratum (every pool gap where a markdown is the best baseline; the pool of 328 gaps yields 7, so the cap of 18 was not reached).
* Pre-registration commit `df272b8` (protocol, scenarios, baselines, pass lines) was pushed before any model call; every `results.json` carries it as `meta.preregistration_commit`.
* One run per scenario, concurrency 6, per-run deadline 120 s, harness spend cap USD 6 (v2) and USD 4 (v1 regression). INVALID (a call to any model other than `gemini-3.5-flash`, or an infra error) may be re-run once, and a scenario INVALID twice is excluded from every count.
* v1's 36 scenarios were re-run once on the new code and prompt (regression), against v1's own frozen baselines.
* No code, prompt, scenario or threshold changed after the first call.

### Results

| | v1 (19 Oct, shipped code, prompt v7) | v2 (new code, new seed, prompt v8) | v1 scenarios re-run on new code (25 + 10, see below) |
|---|---|---|---|
| Beats blanket 20% markdown, n/N | 29 of 36 | 24 of 35 | 30 of 35 (21 of 25, then 9 of 10) |
| Net rupees vs blanket 20% | +₹13,172.82 | +₹70,277.20 | +₹50,477.06 (₹32,902.23 + ₹17,574.83) |
| Rule violations reaching Approve | 0 | 0 | 0 |
| First proposal accepted | 35 of 36 | 29 of 35 | 34 of 35 (24 of 25, 10 of 10) |
| Valid runs, n/36 | 36/36 | 35/36 | 35/36 |
| INVALID count (scenarios excluded after one re-run) | 0 (2 first attempts INVALID, both re-run valid) | 1 (S21); 10 first attempts INVALID | 1 (S03); 8 first attempts INVALID (7 + 1); 10 scenarios NOT RUN in the first pass (spend cap) |
| Latency p50 / p95 | 23.4 s / 38.5 s | 41.5 s / 64.4 s | 28.2 s / 39.3 s (first 25); 37.6 s / 55.6 s (last 10) |
| Cost: per scenario mean / max; total | $0.0802 / $0.1304; $2.8863 | $0.0993 / $0.1573; $3.4752 | $0.0881 / $0.1338; $2.2030 (first 25); $0.0872 / $0.1250; $0.8724 (last 10) |
| Mechanic mix of accepted plays | bundle 23, transfer_plus_nudge 12, usual_order_addon 1 | bundle 23, outlet_markdown 6, markdown 4, coupon 1, transfer_plus_nudge 1 | bundle 24, outlet_markdown 7, coupon 3, markdown 1 |
| Markdown chosen where the best baseline is a markdown, n/N | not defined (no markdown mechanic) | 4 of 7 | not computed (v1 scenarios were not tagged); markdown chosen in 1 of 35 (S31) |
| Estimator upper-bound ratio, median / p10 / min | 0.747 / 0.543 / 0.335 (n=36) | 0.943 / 0.817 / 0.723 (n=35) | 0.880 / 0.743 / 0.614 (first 25); 1.082 / 0.797 / 0.766 (last 10) |

Rupees by which it beats blanket 20% where it does: v1 ₹68,846.22; v2 ₹96,105.07. v2 net against the best blanket depth (10, 20 or 35%): +₹18,897.45. v2 by stratum: feature 20 of 28 beat blanket (net +₹65,225.83); markdown stratum 4 of 7 (net +₹5,051.37). Markdown chosen in total in v2: 4 scenarios. The upper bound is not defined the same way in v1 (best guardrail-passing candidate in the oracle grid) and in v2 (larger of the best allowed markdown and the best legal non-markdown play, `beats_markdown` off), and it is an estimator upper bound, never a best play.

### Pre-registered pass lines

| Line (PROTOCOL_v2.md) | Result | Met |
|---|---|---|
| Beats blanket 20%: at least 30 of 36 | 24 of 35 | No |
| Net rupees vs blanket 20% above 0 | +₹70,277.20 | Yes |
| Markdown where the best baseline is a markdown: at least 5 of 7 | 4 of 7 | No |
| HARD: 0 violations reaching Approve | 0 | Yes |
| Regression: at least 29 of 36 beat blanket 20% | 30 of 35 valid (S03 INVALID twice, 21 of 25 in the first pass) | Yes on 35 valid, with the caveat below |
| Regression: net vs blanket 20% at or above v1's +₹13,172.82 | +₹50,477.06 | Yes |
| Regression: 0 violations | 0 | Yes |

Two of the three v2 performance lines were not met. They are reported as missed and the thresholds were not changed.

### Reading it plainly

* Beats-blanket is not comparable across v1 and v2. The new demand model also changes the blanket 20% baseline itself (it now prices the counterfactual with the same elasticity as the plays), and the v2 seed adds a markdown stratum of 7 scenarios where a markdown is the best baseline by construction. The ratio of 24 of 35 against 29 of 36 therefore does not show a decline in the planner; it also shows a harder baseline in places. The regression run, which holds the scenarios fixed, gives 30 of 35 against v1's 29 of 36.
* Net rupees vs blanket is the more comparable figure and it rose: +₹70,277.20 in v2, +₹50,477.06 on the v1 scenarios (against +₹13,172.82 in v1). It is still a projection under the same estimator on both sides.
* Latency roughly doubled between v1 and v2 (p50 23.4 s to 41.5 s, p95 38.5 s to 64.4 s). The regression run on v1 scenarios sits in between (p50 28.2 s and 37.6 s in its two parts), and its two parts used different concurrency (6 and 3).
* Invalid runs. Almost all were the same cause: 16 of the 18 first-attempt INVALIDs in v2 and the regression (10 + 7 + 1) were a call requested to `gemini-3.5-flash-lite`, and two were infra errors in the regression. v2 had 10 first-attempt INVALIDs, of which 9 re-ran valid and S21 was INVALID twice and excluded. The regression had 7 in its first part (S03 INVALID twice and excluded, 6 re-ran valid) and 1 in the continuation (S32, re-ran valid). The protocol says that more than 6 INVALID runs stops the run. If that is counted by first attempts, both v2 (10) and the regression (7 + 1) went past it and the harness did not stop; if it is counted by scenarios left INVALID after the one re-run, both stayed under it (1 each). The protocol text does not say which. We report both readings.
* The `_cont` folder is not covered by the one-re-run rule. That rule only allows a re-run of an INVALID run. The first regression pass stopped at 25 valid because the harness reserve rule (spent USD 2.29 plus reserved USD 1.50 plus USD 0.30 would pass the USD 4 cap) left S27 to S36 NOT RUN. `_cont` then ran those 10 scenarios (same code, prompt, scenario and baseline files, same pre-registration commit, but a new cap of USD 2.5 and concurrency 3). The protocol sets the cap at USD 4 for the regression and says NOT RUN scenarios are reported; it does not provide for running them afterwards. Total spend of both parts, USD 3.6788, stays under USD 4, and nothing about the code or scoring changed, but this is a continuation that goes beyond the protocol as written, and the combined 35-scenario figures are ours to add together, not a single harness run.
* Markdown is now chosen in 4 of 35 valid v2 scenarios (all 4 in the markdown stratum, none in the feature stratum) and in 1 of 35 on the v1 scenarios. One of the four, S33, still lost to the blanket 20% baseline (₹13,951.14 against ₹18,387.26).

### Limits

* Synthetic tenant and one seed per eval; one run per scenario, so no variance estimate.
* Recovery is projected under Taal's own est-v2 estimator, and the baselines and the planner share it; this is not a real-world outcome.
* Elasticity is assumed (default 1.0 per category in the code, 4.0 in the pre-registered tenant config), not measured; the beats-blanket result moves with it.
* The `markdown` mechanic is scored on a price cut with a node holdout or none, which this eval cannot measure.
* The combined regression figures add two runs with different concurrency and cap.

Diagnosis and fixes follow in the v3 section (pre-registered separately).
