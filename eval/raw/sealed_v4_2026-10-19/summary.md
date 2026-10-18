# Sealed decision-quality eval (2026-10-18)

Label: **measured**. Model gemini-3.5-flash, prompt v10, 36 valid scenarios of 36, concurrency 3, 1 run per scenario (plus one re-run of an INVALID run). Protocol: eval/sealed/PROTOCOL_v4.md.

Recovery is the projected recovery under Taal's own estimator (recovered versus doing nothing) on a synthetic tenant, not a real-world outcome. A fallback play or no play counts as not beating either baseline.

| Metric | Result |
|---|---|
| **PRIMARY: beats blanket 20% markdown** | **19 of 36**; rupees by which it beats it where it does INR 56023.19 (net over all scenarios INR 41995.32) |
| Beats doing nothing | 36 of 36 |
| **HARD: guardrail violations reaching Approve (must be 0)** | **0** |
| Outcomes: model-authored play / deterministic fallback / no play | 36 / 0 / 0 |
| First proposal accepted by the gate; mean iterations | 35 of 36; 1 |
| Latency p50 / p95 (s) | 13.9 / 21.2 |
| Cost per scenario (USD) mean / max; total spend | 0.0342 / 0.0528; 1.2297 |
| Mechanic mix of accepted plays | bundle 28, markdown 8 |
| SECONDARY, estimator upper bound (not a best play): captured ratio median / p10 / min | 0.980 / 0.898 / 0.818 (n=36) |

The upper bound is the larger of the best allowed markdown play and the oracle's best legal non-markdown play (beats_markdown gate off), scored by the same est-v2 estimator; it is not an optimal or best-possible play.


## Markdown option (v2 metrics)

| Metric | Result |
|---|---|
| **Chooses a markdown where the best baseline is a markdown** | **8 of 9** |
| Net rupees vs blanket 20% markdown, all scenarios | INR 41995.32 |
| Net rupees vs the best blanket depth (10/20/35%), all scenarios | INR 3790.14 |
| Markdown chosen, all scenarios | 8 |
| Stratum feature: n / beats blanket 20% / net vs blanket 20% | 27 / 18 / INR 48984.08 |
| Stratum markdown_best: n / beats blanket 20% / net vs blanket 20% | 9 / 1 / INR -6988.76 |

## Legal-baseline view (v3 metrics)

| Metric | Result |
|---|---|
| Beats the best margin-floor-LEGAL blanket depth (0 if none is legal) | 36 of 36 |
| Blanket 20% is floor-illegal in | 36 of 36 scenarios |
| Scenarios where the model-free upper bound exceeds blanket 20% (a legal play can beat it) | 19 |
| Of those, beaten by the planner | 19 |
| Valid runs; mean model calls per run; mean prompt tokens per run | 36; 4; 23332 |

## v4 metrics

| Metric | Result |
|---|---|
| Model turns per run: mean / median / max | 4 / 4.0 / 7 |
| Prompt tokens per run (mean); output + thinking tokens per run (mean) | 23332; 1748 |
| Beats blanket 20%, all valid | 19 of 36 |
| Beats blanket 20% against the ceiling (scenarios where a legal play can) | 19 of 19 |
| Net vs blanket 20%, raw / with a loss-making blanket counted as 0 | INR 41995.32 / INR 28381.60 |
| Turn-count distribution | {'3': 10, '4': 20, '5': 3, '6': 2, '7': 1} |

## By gap type

| Gap type | n | beats blanket |
|---|---|---|
| expiry_writeoff | 18 | 11 |
| online_sellby_breach | 18 | 8 |

## Per scenario

| id | outcome | mechanic | recovery | blanket 20% | upper bound | beats blanket | iterations |
|---|---|---|---|---|---|---|---|
| S01 | model_play | bundle | 2981.51 | 1689.37 | 2913.89 | True | 1 |
| S02 | model_play | bundle | 2360.95 | 1251.34 | 2369.21 | True | 1 |
| S03 | model_play | bundle | 2558.68 | -175.62 | 2959.63 | True | 1 |
| S04 | model_play | bundle | 1099.17 | -232.08 | 1211.51 | True | 1 |
| S05 | model_play | bundle | 3001.07 | -244.60 | 3248.09 | True | 1 |
| S06 | model_play | bundle | 1509.10 | -228.00 | 1600.83 | True | 1 |
| S07 | model_play | bundle | 2424.90 | 2960.92 | 2557.56 | False | 1 |
| S08 | model_play | bundle | 1885.47 | 1941.99 | 1885.68 | False | 1 |
| S09 | model_play | bundle | 2020.36 | 3215.26 | 2019.94 | False | 1 |
| S10 | model_play | bundle | 6007.98 | 4831.37 | 5734.87 | True | 1 |
| S11 | model_play | bundle | 2565.05 | 2496.62 | 2690.59 | True | 1 |
| S12 | model_play | bundle | 2592.51 | 2930.94 | 2757.17 | False | 1 |
| S13 | model_play | bundle | 2981.51 | 2518.61 | 2913.89 | True | 1 |
| S14 | model_play | bundle | 2543.49 | 2834.76 | 2690.59 | False | 1 |
| S15 | model_play | bundle | 2383.31 | 2803.88 | 2557.56 | False | 1 |
| S16 | model_play | bundle | 1885.47 | 2529.28 | 1885.68 | False | 1 |
| S17 | model_play | bundle | 824.28 | 430.69 | 909.80 | True | 1 |
| S18 | model_play | bundle | 2912.08 | 1099.54 | 3268.13 | True | 1 |
| S19 | model_play | bundle | 842.22 | 115.04 | 1029.85 | True | 1 |
| S20 | model_play | bundle | 2748.88 | -1797.99 | 2923.87 | True | 1 |
| S21 | model_play | bundle | 7933.54 | -4454.24 | 8221.38 | True | 1 |
| S22 | model_play | bundle | 1823.92 | 2467.20 | 1823.92 | False | 1 |
| S23 | model_play | bundle | 6921.11 | 662.56 | 6953.76 | True | 1 |
| S24 | model_play | bundle | 2215.58 | -4359.54 | 2468.37 | True | 1 |
| S25 | model_play | bundle | 2565.05 | 3893.82 | 2690.59 | False | 1 |
| S26 | model_play | bundle | 3239.19 | 798.24 | 3609.02 | True | 1 |
| S27 | model_play | bundle | 4015.41 | -2121.65 | 4245.71 | True | 1 |
| S28 | model_play | markdown | 1881.75 | 2932.98 | 1881.75 | False | 1 |
| S29 | model_play | markdown | 2701.47 | 1115.93 | 2701.47 | True | 1 |
| S30 | model_play | markdown | 1525.68 | 2331.01 | 1525.68 | False | 1 |
| S31 | model_play | markdown | 951.18 | 1586.46 | 951.18 | False | 1 |
| S32 | model_play | bundle | 1041.68 | 1740.99 | 1044.06 | False | 1 |
| S33 | model_play | markdown | 3814.60 | 4340.00 | 2754.72 | False | 1 |
| S34 | model_play | markdown | 1571.31 | 2673.11 | 1571.31 | False | 1 |
| S35 | model_play | markdown | 2361.38 | 4144.07 | 2361.38 | False | 1 |
| S36 | model_play | markdown | 3429.90 | 5403.16 | 3429.90 | False | 1 |
