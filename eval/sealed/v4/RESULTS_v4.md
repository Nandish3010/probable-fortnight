## Sealed eval v4 (19 Oct 2026): fewer model turns, a visible gate, a tighter tolerance

Label: measured. Model `gemini-3.5-flash`, asia-south1, prompt v10 (`planner.md` sha256 `285598fd...d1700a4`). Recovery is the projected recovery under Taal's own estimator (versus doing nothing) on a synthetic tenant, not a real-world outcome. Protocol: `eval/sealed/PROTOCOL_v4.md`, pre-registered and pushed at commit `2203349` BEFORE the first test call (it is `meta.preregistration_commit` in the results). Raw files: `eval/raw/sealed_v4_2026-10-19/` (test), `eval/raw/sealed_v4_dev_1..3/` (dev), `eval/raw/sealed_v4_live_2026-10-19.json` (live checks).

### What changed (v3 to v4)

* `estimate_outcomes` returns per draft a `choice_index`, a `gate` verdict (the eight guardrails and `beats_markdown`) and a `reach` figure (consented customers in the draft against all of them); `propose_play` takes `choice_index` and code assembles the play JSON from the estimated draft, so the model no longer writes about 1,200 output tokens of play. The full-play path is unchanged and a test compares five stub runs with the v3 code byte for byte. `check_guardrails` leaves the prompt (it was not in `REQUIRED_ORDER` in v3 either).
* `beats_markdown` tolerance max(INR 50, 2%) (v3: max(500, 5%)).
* Failover: flash asia-south1, flash global, flash-lite; harness backoff kept; live backoff 1 s + 2 s, 3 s cap; tested with a fake 429.
* The code never picks a candidate and nothing is counted as a model play unless the model's `propose_play` was accepted.

### Dev set (tuned on; NOT an independent test)

20 cases from the v2 and v3 scenarios: 14 losses found by `eval/sealed/v4/loss_analysis.md` (27 of 71 recorded plays lost to the best legal alternative or captured under 0.9 of the upper bound; 24 were legal non-markdown plays below the oracle's best (bundle 13, outlet markdown 7, transfer 3, coupon 1; in the cases inspected the draft covered only 207 of 317 or 296 of 334 consented customers, i.e. it left segments out); 3 were plays below the best markdown that the old tolerance let through; 20 of the blanket losses were scenarios where no legal play can beat the floor-illegal blanket) plus 6 control wins. Before = the recorded v2/v3 run of the same scenario.

| Round | Change | Fixed of 14 | Controls kept of 6 | Mean calls | Mean prompt tokens | p50 / p95 | Spend |
|---|---|---|---|---|---|---|---|
| recorded v3 | (v2/v3 code) | 0 | 6 | 6.06 | 51,097 | 31.3 / 42.3 s | |
| dev 1 | turns, gate in estimate, choice_index, tolerance, failover | 2 | 4 (D15, D16 worse) | 4.05 | 22,953 | 14.5 / 26.4 s | $0.69 |
| dev 2 | + `reach` in the estimate and the prompt line to list every segment | 10 | 6 | 3.95 | 22,579 | 16.7 / 22.3 s | $0.67 |
| dev 3 | dev 2 + thinking `minimal` on routing turns | 8 | 6 | 4.05 | 21,040 | 20.6 / 26.3 s | $0.50 |

Dev 3 was worse on decisions and not faster, so it was reverted (thinking stays low / low). Dev 2 is the frozen code. The four losses still open in dev 2 (D01, D02, D04, D05) are bundles whose partner or price differs from the oracle's, where the estimator ignores discount depth; they were not tuned further. Dev spend $1.86 of a $5 cap.

### Test (independent: seed 86213547, 36 scenarios, run once, pre-registered)

| | v1 (shipped code, own seed) | v2 (own seed) | v3 (own seed) | **v4 (fresh seed)** |
|---|---|---|---|---|
| Beats blanket 20%, n / valid | 29 / 36 | 24 / 35 | 17 / 36 | **19 / 36** |
| Against the ceiling (scenarios where a legal play can beat blanket 20%) | n/a | 24 / 25 valid | 17 / 18 | **19 / 19** |
| Net vs blanket 20%, raw | +13,172.82 | +70,277.20 | -10,319.64 | **+41,995.32** |
| Net vs blanket 20%, loss-making blanket counted as 0 | n/a | n/a | -24,363.71 | **+28,381.60** |
| Violations reaching Approve | 0 | 0 | 0 | **0** |
| Valid runs | 36 / 36 | 35 / 36 | 36 / 36 | **36 / 36** |
| Latency p50 / p95 | 23.4 / 38.5 s | 41.5 / 64.4 s | 31.3 / 42.3 s | **13.9 / 21.2 s** |
| Model calls per run (mean) | n/a | 6 (median) | 6.06 | **4.0 (3 to 7)** |
| Prompt tokens per run (mean) | n/a | n/a | 51,097 | **23,332** |
| Cost per scenario (mean) / total | $0.080 / $2.89 | $0.099 / $3.48 | $0.094 / $3.37 | **$0.034 / $1.23** |
| First proposal accepted | 35 / 36 | 29 / 35 | 32 / 36 | **35 / 36** |
| Markdown where the best baseline is a markdown | n/a | 4 / 7 | 14 / 15 | **8 / 9** |
| Beats the best margin-floor-legal blanket | n/a | n/a | 35 / 36 | **36 / 36** |
| Upper-bound capture median / min | 0.747 / 0.335 | 0.943 / 0.723 | 0.998 / 0.507 | **0.980 / 0.818** |
| Mechanic mix | bundle 23, transfer 12, add-on 1 | bundle 23, outlet 6, markdown 4, coupon 1, transfer 1 | bundle 16, markdown 14, outlet 4, transfer 2 | bundle 28, markdown 8 |

The four generations used four different seeds, so the columns are not paired and the net-rupee rows depend on the scenarios (v4's seed has a markdown stratum of 9, v3's of 15). The paired comparison is the dev set, which was tuned on and proves nothing independent.

### Pre-registered pass lines (PROTOCOL_v4.md)

| Line | Result | Met |
|---|---|---|
| Latency p50 at most 25 s | 13.9 s | Yes |
| Valid runs at least 34 of 36 | 36 of 36 (no INVALID attempt, 0 failed calls, all 144 calls to `gemini-3.5-flash`) | Yes |
| HARD: 0 violations at Approve | 0 | Yes |
| Beats blanket within 1 of the ceiling (at least 18 of 19) | 19 of 19 | Yes |
| Net vs max(0, blanket 20%) above 0 | +INR 28,381.60 | Yes |

### Live checks on the v4 code (local API, real model, `eval/raw/sealed_v4_live_2026-10-19.json`)

* Plan live, Tea gap, 3 runs: status done, `planner_source=model` (`live_gemini`) each time, 12.2 / 10.7 / 9.1 s, 2 tool calls (estimate, propose), mechanic transfer_plus_nudge, margin INR 9,716.02 under est-v2.
* Plan live, Quinoa gap, 3 runs: done, `planner_source=model`, 13.7 / 19.7 / 15.2 s (3, 5 and 3 tool calls), bundle, margin INR 1,110.87 / 1,165.59 / 758.40.
* Approve on the recorded Tea play (unchanged by v4): 355 treated / 39 held out; expected margin INR 9,191.29; blanket 20% INR 32,015.18 (do nothing INR 35,020.00); beat over the blanket INR 6,186.47 (the hero figure, `test_tea_hero_play_is_unchanged` passes).
* A live Tea re-plan lands on INR 9,716.02, not the recorded INR 9,191.29: the recording was made under est-v1 and the live run is projected under est-v2. Both are shown as what they are.

### Notes for the web and the API

No payload field changes (`docs/schemas/tools/planner.*` gained fields; the play schema is unchanged). The trace panel (`web/components/traceRows.tsx`) summarises a `propose_play` call from `args.play`; a v4 call carries `choice_index` instead, so its row reads "draft a play" and the trace record has no `rationale` for the attempt (the play card still shows the assembled rationale). The plan-progress steps (`web/lib/planSteps.ts`) work from the `propose_play` response and `estimate_outcomes`, so they still advance. A one-line web change (show `choice_index` in the row) is optional and is the UI session's file.

### Limits

Synthetic tenant; four seeds, one per generation, one run per scenario; projections under est-v2 with an assumed elasticity of 4.0; baselines and planner share the estimator, which is flat in discount depth, so the oracle's best bundle is a shallow-discount one and the capture ratio can exceed 1; the blanket 20% counterfactual is priced generously and is floor-illegal everywhere (reported raw and with max(0, blanket)); the dev set was tuned on (the `reach` figure and the audience line in the prompt came from its loss analysis), so only the fresh-seed test counts; the test seed has 9 markdown-best scenarios, where the model beats the (generous) blanket in only 1 of 9; the live checks are on a local API running the v4 code, not the deployed service.
