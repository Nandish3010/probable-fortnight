# Sealed baseline eval protocol (pre-registered, 19 Oct 2026)

This file, `scenarios.json`, `baselines.json` and `cell_report.json` are committed and pushed BEFORE any model call.
The pushed commit is the pre-registration; its sha is recorded in `results.json` (`meta.preregistration_commit`).
Nothing here is edited after the first model call. Phase A (oracle, harness, scenarios) made zero model calls.

## 1. What is tested

Whether the plays Taal's planner accepts beat two simple baselines on gaps it has never seen: doing nothing, and
the product's own blanket 20% markdown counterfactual. The real planner (`agents.planner.run.run_planner_async`, as
the product runs it) runs once on each frozen scenario. A model-free oracle (`eval/sealed/oracle.py`) supplies a
secondary figure, an estimator upper bound, which is NOT a best play (section 7).

Fixed: model `gemini-3.5-flash` (config/models.toml `ids.flash`), asia-south1; planner prompt v7 (top entry of
`agents/planner/prompts/CHANGELOG.md`; `planner.md` sha256 0b2160586f3b0df940803c4598881e09835adb3b747a0792c4148ae8a3ade684,
also recorded in `results.json`); shipped thinking settings (`[thinking]` planner_route = low, planner_final = low;
temperature 0.2); LoopAgent max 3 iterations; the same tools (get_gap, get_candidate_audiences, get_past_plays,
estimate_outcomes, check_guardrails, propose_play); per-run deadline 120 s; `TAAL_NOW=2026-09-12T03:30:00Z`.
No product code is changed.

## 2. Scenarios

* Seed 40617833 (`python -m data.generator --seed 40617833`, then `python -m jobs.sense`). Grep proof: the number
  appears nowhere else in the repo (tracked files, fixtures, `agents/planner/evalsets`, `eval/raw`, traces) before
  this change, and is not the demo seed 20260912. One seed was enough; no second seed was used.
* Pool: gap type online_sellby_breach or expiry_writeoff, at least INR 500 at stake (the planner threshold), lot 10
  to 500 units, deadline 3 to 40 days from the as-of date, not one of the generator's planted demo gaps.
* Stratified by features, not by any oracle answer: 18 cells = gap type (2) x lot band (10-60 / 61-200 / 201-500
  units) x deadline band (3-10 / 11-21 / 22-40 days), 2 gaps per cell = 36. Inside a cell: sort by
  sha256("sealed-v2|40617833|" + gap_id), take the first 2. A cell with fewer than 2 borrows from the nearest cell
  of the same gap type (Manhattan distance over the band indices, ties to the lower pair), recorded per scenario as
  `borrowed_from`. Selection rule is also in the docstring of `eval/sealed/make_scenarios.py`.
* Cell counts and borrowing: `cell_report.json`. The generator's lots are small and its deadlines short (pool of
  306 gaps; the 22-40 day band is empty and only one gap exceeds 200 units), so 21 of the 36 scenarios are
  borrowed. The spread actually achieved is therefore narrower than the cell design: lots 10 to 280 units
  (median 34), deadlines 3 to 14 days, margin 10% to 23% of price, consented audience 308 to 458. This is stated
  with the results; it is a property of the synthetic generator.
* Margin level and consented-audience size are recorded per scenario (`features`).
* sha256: `scenarios.json` 4faafc4673679c946ec8178eb83fba0c59dc50cb409bc6b9e2e6ebd767f69c8f;
  `baselines.json` 3c4a43e44d4dc22c8eaef2e4b4fb07b809e089debc5fd403e3bb534e4c1cbd33;
  `cell_report.json` 58b29e394ba048c83abeb2c7cf80876a96e745a6e8ed3a1df4d9068ea329d5a2.

## 3. Baselines (no model)

`baselines.json`, per scenario, from the SAME estimator (`agents/gate/estimator.py`) the product uses:

* Recovery of a play = `do_nothing_inr + play_net_inr`: recovered versus doing nothing, the figure behind the demo
  Tea play's INR 9,191.29. Doing nothing = 0.
* Blanket 20% markdown = `do_nothing_inr - blanket_markdown_inr` (Tea: 3,004.82). It can be negative: where the
  markdown gives away more margin than the forecast write-off it prevents, any positive-recovery play beats it.
  `baselines.json` shows which scenarios have a negative baseline; the results report that count.
* Estimator upper bound: the highest recovery among the oracle's candidates that pass every guardrail
  (definition in the docstring of `eval/sealed/oracle.py`; about 6,000 candidates per gap; legality = the product's
  own `propose_play`; tests in `tests/unit/test_sealed_oracle.py`). Top 3 mechanic classes are recorded.

## 4. Metrics and pass lines

All reported for the valid scenarios, in full, unchanged. A deterministic-fallback play, or no play, counts as NOT
beating either baseline (recovery 0 for the secondary ratio).

| Metric | Definition | Pass line |
|---|---|---|
| PRIMARY: beats blanket 20% | model-authored accepted play with recovery above the blanket baseline; n of 36 and rupees beaten by | **at least 30 of 36 (pre-registered)** |
| Beats doing nothing | model-authored accepted play with recovery above 0; n of 36 | reported, no line |
| HARD: guardrail violations reaching Approve | accepted plays failing a fresh `guardrails.check`, the money invariant or the holdout audit | **0 (hard requirement)** |
| Outcomes | model-authored play / deterministic fallback / no play | reported, no line |
| First proposal accepted; mean iterations | first `propose_play` valid; ADK model turns | reported, no line |
| Latency p50 / p95; cost per scenario; total spend | wall time; list-price cost from the tap | reported, no line |
| Mechanic mix of accepted plays | count per mechanic | reported, no line |
| SECONDARY, estimator upper bound | accepted recovery / upper bound: median, p10, min | reported, no line; never called optimal or best possible |

## 5. Runs, validity, spend

* Runs: 1 per scenario, concurrency 4 (`--concurrency 4`, recorded in `results.json`); each scenario runs on its own
  copy-on-write sandbox of its tenant. Budget basis: `planner_cost_per_play` USD 0.0777 (eval/raw/live_eval_2026-10-14/
  summary.json, 46 plays, list prices): about USD 2.80 for 36 runs, at most about USD 5.60 if every run is re-run once.
* INVALID = any call requested of or answered by a model other than `gemini-3.5-flash` (tap check of the requested
  model and the server-reported `model_version`), a planner timeout or model-unavailable fallback, or an infra or
  harness error. An INVALID run may be re-run once; nothing else may be re-run. The original is kept. A scenario
  INVALID twice is reported and excluded from every count. If more than 6 runs are INVALID, the run stops and is reported.
* Spend cap USD 10 at list prices (config/models.toml). Enforced in the harness (`harness/sealed_eval.py`,
  tap from `harness/adversarial_eval.py`): the tap refuses any call when spend plus USD 0.15 would reach the cap; a
  run starts only if spend + the reserves of runs in flight + its own USD 0.30 reserve fits the cap. Runs not
  started are NOT RUN and reported.
* Output: `eval/raw/sealed_2026-10-19/` with `runs/*.json`, `model_calls.jsonl`, `spend_ledger.json`,
  `results.json`, `summary.md`.

## 6. Reporting

Results are reported in full, unchanged, whatever they are. No re-rolls, no extra runs, no scenario swaps.

## 7. Limits (stated with every number)

* The tenant is synthetic and the scenarios come from one generator seed; lots are small and deadlines short.
* Recovery is a projection under Taal's own estimator, not a measured outcome. The baselines and the upper bound use
  the same estimator as the planner's tools, so this measures decision quality inside Taal's economic model.
* The estimator's response rate does not depend on the discount depth or on the mechanic (a flat Beta prior), and it
  counts a bundle's full bundle price per responding unit. Consequences: within a mechanic the estimator is
  indifferent to discount depth; a bundle out-recovers a coupon or a transfer whenever it clears the margin floor
  (on this seed the oracle's top class is a bundle in most scenarios); and doing nothing is never the estimator's best.
  The oracle is therefore only an estimator upper bound that favours a lowest-discount bundle (5% grid minimum). It
  ignores the tenant's soft policy text, which the planner is told to follow. It is never "optimal" or "best possible".
* One run per scenario: no variance estimate across repeated runs.
