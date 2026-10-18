# Sealed eval v3: markdown option after the v2 diagnosis (pre-registered, 19 Oct 2026)

This file, `v3/scenarios.json`, `v3/baselines.json` and `v3/cell_report.json` are committed and pushed BEFORE any v3 model
call; the pushed commit is the pre-registration (its sha goes in `results.json`, `meta.preregistration_commit`). Nothing
here, and no product code or prompt, changes after the first v3 call. v1, v2 and the v1 regression
(`eval/raw/sealed_2026-10-19/`, `sealed_v2_2026-10-19/`, `sealed_v1_regression_2026-10-19*/`) are not touched and not re-run.
The diagnosis that motivates the changes is in `eval/evaluation.md` ("Sealed eval v2: diagnosis").

## 1. What changed since v2 (and only this)

* Harness: default concurrency 3 (v2 ran 6, with two other jobs sharing the quota); backoff-and-retry on a 429 (up to 4
  tries, 2/4/8/16 s with jitter) BEFORE the SDK fails over to `gemini-3.5-flash-lite`, so a throttled run stays on the primary model;
  each scenario's tenant is built once before the runs start (two v1-regression runs died on a concurrent first build).
* Tool output: `estimate_outcomes` states the best-markdown reference once (first result), not in every result.
* Prompt v9 (`planner.md` sha256 `8c786dde4621beb21a892d826ffba3f9602cd0fb1dbbf4b4f9717cea6187f98b`): the reference-once note, and
  "a citation ref is an id, never a rupee figure".
* Gate message for an outlet node is worded correctly. No guardrail rule, no `beats_markdown` tolerance, no estimator change.
  The diagnosis found nothing in the gate to change: in v2 no run was rejected by `beats_markdown`, and no run lost to the blanket
  because the gate was lenient (every accepted play was within tolerance of, or above, the best markdown the margin floor allows).

Fixed as before: model `gemini-3.5-flash` (asia-south1), shipped thinking settings, LoopAgent max 3, same six tools, per-run
deadline 120 s, `TAAL_NOW=2026-09-12T03:30:00Z`, tenant config as committed (clearance exception OFF).

## 2. Scenarios

* Seed 53718294 (`python -m data.generator --seed 53718294`, then `python -m jobs.sense`). Grep proof before the scenario
  file was written: the number is in no tracked file, fixture, evalset, `eval/raw` or trace; it is not 20260912, 40617833 or 71903482.
* Same design and selection code as v2 (`python -m eval.sealed.make_scenarios_v2 --seed 53718294 --version 3`): markdown stratum =
  every pool gap with `markdown_is_best_baseline` (15 here, cap 18), the rest by v1's cell rule (21 scenarios); 11 of 36 borrowed
  from neighbouring cells; deadlines 3 to 12 days, lots 10 to 236 units.
* v3 baselines add three fields (v2's files are unchanged): `blanket_legal_recovery_inr` (the best blanket depth whose net margin
  clears the category floor; 0 if none), `blanket20_is_floor_legal`, `upper_bound_beats_blanket20` (can any legal play beat the
  blanket 20% figure at all).
* **Stated ceiling:** a 20% cut is floor-illegal in 36 of 36 scenarios, and in only 18 of 36 does ANY legal play exceed the blanket
  20% figure (`upper_bound_beats_blanket20`). A line of "30 of 36 beat blanket 20%" is therefore unreachable on this seed
  (v2: 26 of 36 reachable, 24 reached of 25 valid ones). The primary line below is stated against that ceiling.
* sha256: `v3/scenarios.json` 31c495ea1b321dd29a4225f76c2b486c1b2705f684ee255e4018731a4156cea4;
  `v3/baselines.json` e91d363e671abb7d8a3f9a12818bc643d0702b808ab4cfa61e20a1ac2d4fbc86;
  `v3/cell_report.json` af45a20be7677f78f4b54309b40ceccb8048b4bae10031e071f88684686dc68a.

## 3. Metrics and pass lines (stated now, never changed after)

| Metric | Definition | Pass line |
|---|---|---|
| PRIMARY: beats blanket 20% (v1's definition), among the 18 ceiling scenarios | accepted model play with recovery above the blanket 20% figure, among scenarios with `upper_bound_beats_blanket20` | **at least 15 of 18** |
| Beats blanket 20%, all 36 (v1's reading) | n of 36 | reported; ceiling 18 |
| Beats the best margin-floor-LEGAL blanket depth, all valid | recovery above `blanket_legal_recovery_inr` | **at least 34 of 36** |
| Net rupees vs blanket 20% | sum over valid scenarios | **above 0** |
| Markdown where the best baseline is a markdown | n of N (N = 15 by the file) | **at least 10 of N** |
| HARD: violations reaching Approve | fresh `guardrails.check`, money invariant, holdout audit, `beats_markdown` re-check | **0** |
| Valid runs | scenarios VALID after the one allowed re-run | **at least 34 of 36** |
| Planner latency p50 | wall time of valid runs | **at most 30 s** |
| Reported, no line | latency p95, cost, first proposal accepted, model calls and prompt tokens per run, mechanic mix, per-stratum splits, upper-bound capture, INVALID count and causes |  |

A deterministic-fallback play or no play counts as not beating any baseline.

## 4. Runs, validity, spend

1 run per scenario; concurrency 3; `--retry-429 4`; spend cap USD 8 (`--cap-usd 8`); output
`eval/raw/sealed_v3_2026-10-19/`. INVALID (any call to or answered by a model other than `gemini-3.5-flash`, planner timeout
or model-unavailable fallback, infra or harness error) may be re-run once; INVALID twice is reported and excluded; more than 6
INVALID attempts: stop and report (checked at the end, as the harness has no automatic stop). NOT RUN scenarios (cap) are
reported and may NOT be completed by a continuation run. No other job uses the model while v3 runs.

## 5. Reporting and limits

Everything is reported in full next to v1, v2 and the regression, whatever it shows. No re-runs, no scenario swaps, no
threshold change. Limits as v2: synthetic tenant, one seed, projections under est-v2 whose elasticity (4.0) is an assumption,
baselines and planner share the estimator, one run per scenario, the markdown's node holdout or absence of one cannot be
measured here; the blanket 20% baseline is floor-illegal everywhere and is kept only for comparability with v1.
