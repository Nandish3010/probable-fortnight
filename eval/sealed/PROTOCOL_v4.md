# Sealed eval v4: fewer model turns and a visible gate (pre-registered, 19 Oct 2026)

This file, `v4/scenarios.json`, `v4/baselines.json` and `v4/cell_report.json` are committed and pushed BEFORE any v4 test
call; the pushed commit is the pre-registration (its sha goes in `results.json`, `meta.preregistration_commit`). Nothing here, and
no product code or prompt, changes after the first test call. v1, v2, v3 and the regression runs are not touched and not re-run.

## 1. What changed since v3 (code at the pre-registration commit)

1. **Turns.** `estimate_outcomes` returns, per draft, `choice_index`, a `gate` verdict (the eight guardrails and the
   `beats_markdown` result) and a `reach` figure; `propose_play` accepts `choice_index` (+ an optional short `rationale`) and code
   assembles the play from the estimated draft. The full-play path is unchanged (a test replays five stub runs and compares the
   play JSON, the propose_play arguments and the tool sequence with the v3 code byte for byte). `check_guardrails` is out of the
   prompt (it was already out of `REQUIRED_ORDER`) and stays registered. A draft needs only gap_id, mechanic, mechanic_params and
   audience.segment_ids; code fills the rest from the gap. Prompt v10 (`planner.md` sha256
   `285598fdb3fa5fd5ab9cb0e79ef77394f8bae2821a158a5fd6e8c0956d1700a4`).
2. **Tolerance.** `beats_markdown` tolerance max(INR 50, 2%) (v3: max(500, 5%)), in `config/tenant.demo.toml`.
3. **Failover.** gemini-3.5-flash asia-south1, then gemini-3.5-flash global, then gemini-3.5-flash-lite (global). The harness keeps its
   SDK-level 429 backoff (2/4/8/16 s, 4 tries); the live path backs off 1 s and 2 s (jittered, 3 s cap) on a 429 before failing over.
   Tested with a fake 429. A call answered by the global endpoint of the same model is not INVALID; a call to the lite model still is.
4. **No code override.** Code never picks a candidate: the model's `choice_index` is the choice. A play is counted as a model play
   only when `propose_play` was called by the model and accepted.
5. **Harness.** The v3 block of `results.json` is no longer overwritten by the v2 block (a reporting bug found after v3; the v3
   numbers recomputed in `eval/raw/sealed_v3_2026-10-19/metrics_recomputed.json` are used). New metrics: model turns per run,
   tokens, beats-blanket against the ceiling, net vs blanket raw and with max(0, blanket).

Thinking levels are unchanged (low / low): a dev round with `minimal` on the routing turns was worse and was reverted.
Fixed as before: model `gemini-3.5-flash` (asia-south1), LoopAgent max 3, per-run deadline 120 s, `TAAL_NOW=2026-09-12T03:30:00Z`,
tenant config as committed (clearance exception OFF), concurrency 3, `--retry-429 4`, cap USD 8.

## 2. Dev set and test set (stated plainly)

* **Dev set (tuned on; not an independent test).** 20 cases taken from v2 and v3 (14 losses found by `v4/loss_analysis.md`, 6 control
  wins), `v4/dev_scenarios.json`. Three rounds, `eval/raw/sealed_v4_dev_1..3/`; spend USD 1.86 of the USD 5 dev cap. The changes above
  and the `reach` figure were chosen on it. Round 2 (the frozen code): 10 of 14 losses fixed, 6 of 6 controls kept, mean 3.95 model
  calls, p50 16.7 s. These numbers are NOT the result.
* **Test set (independent).** Seed 86213547 (`python -m data.generator --seed 86213547`, then `python -m jobs.sense`). Grep proof run
  over every file under the workspace (repo, worktrees, coordination, eval/raw, traces) before the scenario file was written: the
  number appears nowhere, and it is not 20260912, 40617833, 71903482 or 53718294. Same design and selection code as v3
  (`python -m eval.sealed.make_scenarios_v2 --seed 86213547 --version 3 --out eval/sealed/v4`): 36 scenarios; markdown stratum = every
  pool gap with `markdown_is_best_baseline` (9 here, cap 18); the other 27 by v1's cell rule (15 borrowed from neighbouring cells); lots 10
  to 248 units, deadlines 3 to 13 days.
* **Stated ceiling:** blanket 20% is floor-illegal in 36 of 36; in 19 of 36 ANY legal play exceeds the blanket 20% figure.
* sha256: `v4/scenarios.json` 7f47df8f070aa6f46fee391c5f09e8b68b831884e9a4dba39e27a2c8cc6817cb;
  `v4/baselines.json` 04736ae67c2dcc07f3233795d6e7d477f797f2baea221eea87c8e8ab81c607ee;
  `v4/cell_report.json` 717ca7fd38921e0d1b71e29308dfc2bf37f3122df09fd6f9ef719d4a364a6aa6.

## 3. Pass lines (fixed now, never changed)

| Metric | Definition | Pass line |
|---|---|---|
| Latency p50 | wall time of valid runs | **at most 25 s** |
| Valid runs | VALID after the one allowed re-run | **at least 34 of 36** |
| HARD: violations reaching Approve | fresh `guardrails.check`, money invariant, holdout audit, `beats_markdown` re-check | **0** |
| Beats blanket 20% vs the ceiling | model plays above the blanket 20% figure, among the 19 ceiling scenarios | **within 1 of the ceiling (at least 18 of 19)** |
| Net rupees vs max(0, blanket 20%) | sum over valid scenarios of recovery minus max(0, blanket20) | **above 0** |
| Reported, no line | beats blanket on all 36; net vs blanket raw; model turns per run; prompt and output tokens; p95; cost; first proposal accepted; markdown where the best baseline is a markdown (n of 9); beats the best legal blanket; mechanic mix; upper-bound capture; INVALID count and causes | |

The blanket 20% counterfactual is scored as in v1 to v3 (not redefined): it prices cleared units at cost minus discount on baseline
units, and counts as possible where 20% is below the margin floor or the lot is past its online sell-by. Net vs blanket is therefore
reported raw and with a loss-making blanket counted as 0; v3 had net vs max(0, blanket) of INR -24,363.71 on its seed, so that line may fail.
A deterministic-fallback play or no play counts as not beating any baseline.

## 4. Runs, validity, spend

1 run per scenario; concurrency 3; `--retry-429 4`; cap USD 8; output `eval/raw/sealed_v4_2026-10-19/`. INVALID (a call to a
model other than `gemini-3.5-flash`, planner timeout or model-unavailable fallback, infra or harness error) may be re-run once; INVALID
twice is reported and excluded; more than 6 INVALID attempts: stop and report. NOT RUN scenarios (cap) are reported and not completed.
No other job uses the model while the test runs.

## 5. Reporting and limits

Everything is reported next to v1, v2 and v3, whatever it shows; no re-runs, no scenario swaps, no threshold change. Limits as v2/v3:
synthetic tenant, one seed, projections under est-v2 whose elasticity (4.0) is an assumption, baselines and planner share the
estimator (which is flat in discount depth, so the oracle's best bundle is a shallow-discount one), one run per scenario.
