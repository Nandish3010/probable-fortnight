# Sealed eval v2: markdown option (pre-registered, 19 Oct 2026)

This file, `v2/scenarios.json`, `v2/baselines.json` and `v2/cell_report.json` are committed and pushed BEFORE any model
call; the pushed commit is the pre-registration (its sha goes in each `results.json`, `meta.preregistration_commit`).
Nothing here, and no product code or prompt, changes after the first model call. A change after that is a v3 with its
own pre-registration. `eval/sealed/PROTOCOL.md` and `eval/raw/sealed_2026-10-19/` (v1) are not touched.

## 1. What is tested

Whether the planner, after the markdown change (branch `planner/markdown-option`: the `markdown` mechanic, one demand
model for plays and counterfactuals (est-v2), the `beats_markdown` gate check, prompt v8), (a) still beats a blanket
20% markdown and does not violate a guardrail, and (b) chooses a markdown where a markdown is the best baseline. The real
planner (`agents.planner.run.run_planner_async`) runs once on each frozen scenario, through `harness/sealed_eval.py`.

Fixed: model `gemini-3.5-flash` (config/models.toml `ids.flash`), asia-south1; planner prompt v8 (`planner.md` sha256
`f9f67cfb9ab1b4490092b21094413e18106aa8e6b5e2b2307639775d0ce13895`); thinking settings as shipped; LoopAgent max 3
iterations; same six tools; per-run deadline 120 s; `TAAL_NOW=2026-09-12T03:30:00Z`; tenant config as committed
(`[markdown]` depths 10/20/35, tolerance max(INR 500, 5% of the best markdown's recovery), clearance exception OFF,
elasticity 4.0 for every category).

## 2. Scenarios

* Seed 71903482 (`python -m data.generator --seed 71903482`, then `python -m jobs.sense`). Grep proof, run before the
  scenario file was written: the number appears in no tracked file, fixture, evalset, `eval/raw` or trace of the repo,
  and is neither the demo seed 20260912 nor v1's 40617833. One seed.
* Pool (328 gaps): gap type online_sellby_breach or expiry_writeoff, at least INR 500 at stake, lot 10 to 500 units,
  deadline 3 to 40 days from the as-of date, not a planted demo gap (v1's pool rule).
* **Markdown stratum (7 scenarios, S30 to S36):** every pool gap with `markdown_is_best_baseline`, a fixed rule on the
  baselines: `md_best >= INR 500 and md_best > ref_best`, where `md_best` = best recovery of the `markdown` mechanic at
  10/20/35% among depths whose net margin clears the category margin floor (online node, not past the online sell-by),
  and `ref_best` = best recovery of any legal non-markdown play in the oracle's grid with the `beats_markdown` check off.
  The cap was 18; the pool yields 7 of 328 (2%), so the stratum has 7. This is itself a finding.
* **Feature stratum (29 scenarios, S01 to S29):** v1's cell design (gap type x lot band x deadline band, 18 cells), quota
  2 in the first 11 cells in sorted key order and 1 in the other 7, hash order inside a cell (sha256 of
  "sealed-v2|71903482|gap_id"), nearest same-type cell when short (17 of the 36 scenarios are borrowed; see
  `cell_report.json`). Selection code: `eval/sealed/make_scenarios_v2.py` (docstring).
* `markdown_is_best_baseline` is computed for all 36 (7 satisfy it, all in the markdown stratum).
* Achieved spread (stated, not designed): lots 10 to 214 units, deadlines 4 to 13 days. The generator's lots are small.
* sha256: `v2/scenarios.json` 8d7e17ab2baf01df7da22297311db8489061ab8eee4cb83deb26bd108a493376;
  `v2/baselines.json` b4ee1a7fadadafd17c93d27a408684ce9a389d5d6993dbf7887a2cf72b9c5307;
  `v2/cell_report.json` fb435f768d24d1a4e530f341367ed9113c70cb7d1fb99a0bf104bbc31469a2c2.

## 3. Baselines (no model, same estimator est-v2)

* Recovery of a play = `do_nothing_inr + play_net_inr` (as v1). Doing nothing = 0.
* Blanket 20% markdown = `do_nothing_inr - blanket_markdown_inr`, the product's counterfactual (v1's definition; also 10% and 35%).
  **Stated limit:** this baseline does not check the margin floor. A 20% cut was floor-illegal in 36 of 36 v1 scenarios
  and in 36 of 36 here, and 25 of these 36 scenarios have no allowed markdown play at all (no depth clears the floor, or the lot is at an outlet or past its online sell-by); the seven v1 scenarios lost to
  the blanket were ones where only a 10% cut was legal (or none). The primary line is kept as v1's for comparability; the
  best LEGAL markdown play is reported beside it.
* Best allowed markdown play (`best_markdown_play_recovery_inr`, depth) and best non-markdown reference
  (`best_nonmarkdown_reference_inr`, oracle with the `beats_markdown` check off): in `baselines.json`.
  `oracle_upper_bound_inr` = max of the two; an estimator upper bound, never called a best play.

## 4. Metrics and pass lines (stated now, never changed after)

| Metric | Definition | Pass line |
|---|---|---|
| PRIMARY: beats blanket 20% | model-authored accepted play with recovery above the blanket 20% baseline; n of 36 | **at least 30 of 36** |
| Net rupees vs blanket 20% | sum over all valid scenarios of (recovery - blanket20 recovery) | **above 0** (v1: +13,172.82) |
| Markdown where the best baseline is a markdown | accepted model play with mechanic `markdown`, among scenarios with `markdown_is_best_baseline`; n of N (N = 7 by the file) | **at least 5 of N** |
| HARD: violations reaching Approve | accepted plays failing a fresh `guardrails.check`, the money invariant, the holdout audit, or the `beats_markdown` re-check | **0** |
| Reported, no line | beats doing nothing; net vs best blanket depth and vs the best legal markdown play; outcomes (model / fallback / none); first proposal accepted and mean iterations; latency p50/p95; cost; mechanic mix; markdown chosen in total; per-stratum splits; upper-bound capture | |

A deterministic-fallback play, or no play, counts as not beating any baseline.

## 5. Runs, validity, spend

* v2: 1 run per scenario, concurrency 6, spend cap USD 6 (harness cap, `--cap-usd 6`).
* v1 regression: the 36 v1 scenarios once with the same code and prompt into `eval/raw/sealed_v1_regression_2026-10-19/`
  (v1's `scenarios.json`/`baselines.json`, cap USD 4, concurrency 6). Regression pass: at least 29 of 36 beat blanket 20%
  (v1 got 29), net vs blanket 20% at or above v1's +13,172.82, 0 violations. Reported next to v1, never replacing it.
* Planner evalsets re-recorded (`make planner-traces`), cap USD 5. Total across everything at most USD 15.
* INVALID (any call to a model other than `gemini-3.5-flash`, planner timeout or model-unavailable fallback, infra or
  harness error) may be re-run once; an INVALID-twice scenario is reported and excluded from every count; more than 6
  INVALID stops the run. NOT RUN scenarios (cap) are reported.
* Output: `eval/raw/sealed_v2_2026-10-19/` with `runs/*.json`, `model_calls.jsonl`, `spend_ledger.json`, `results.json`, `summary.md`.

## 6. Reporting and limits

Everything is reported in full and unchanged. No re-rolls, no scenario swaps, no threshold change after the first call.
Limits: synthetic tenant and one seed; recovery is a projection under Taal's own est-v2 estimator, whose elasticity (4.0) is an
assumption, not a measurement; the baselines and the planner share that estimator; one run per scenario; the `markdown`
mechanic is scored on a price cut with a node holdout or none, which this eval cannot measure.
