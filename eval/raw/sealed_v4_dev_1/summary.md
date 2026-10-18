# Sealed decision-quality eval (2026-10-18)

Label: **measured**. Model gemini-3.5-flash, prompt v10, 20 valid scenarios of 20, concurrency 3, 1 run per scenario (plus one re-run of an INVALID run). Protocol: DEV set, tuned on; not an independent test.

Recovery is the projected recovery under Taal's own estimator (recovered versus doing nothing) on a synthetic tenant, not a real-world outcome. A fallback play or no play counts as not beating either baseline.

| Metric | Result |
|---|---|
| **PRIMARY: beats blanket 20% markdown** | **14 of 20**; rupees by which it beats it where it does INR 41958.73 (net over all scenarios INR 22635.33) |
| Beats doing nothing | 20 of 20 |
| **HARD: guardrail violations reaching Approve (must be 0)** | **0** |
| Outcomes: model-authored play / deterministic fallback / no play | 20 / 0 / 0 |
| First proposal accepted by the gate; mean iterations | 20 of 20; 1 |
| Latency p50 / p95 (s) | 14.5 / 26.4 |
| Cost per scenario (USD) mean / max; total spend | 0.0345 / 0.0578; 0.6908 |
| Mechanic mix of accepted plays | bundle 16, markdown 3, transfer_plus_nudge 1 |
| SECONDARY, estimator upper bound (not a best play): captured ratio median / p10 / min | 0.840 / 0.658 / 0.578 (n=20) |

The upper bound is the larger of the best allowed markdown play and the oracle's best legal non-markdown play (beats_markdown gate off), scored by the same est-v2 estimator; it is not an optimal or best-possible play.


## Markdown option (v2 metrics)

| Metric | Result |
|---|---|
| **Chooses a markdown where the best baseline is a markdown** | **3 of 6** |
| Net rupees vs blanket 20% markdown, all scenarios | INR 22635.33 |
| Net rupees vs the best blanket depth (10/20/35%), all scenarios | INR -16507.01 |
| Markdown chosen, all scenarios | 3 |
| Stratum feature: n / beats blanket 20% / net vs blanket 20% | 14 / 9 / INR 9345.76 |
| Stratum markdown_best: n / beats blanket 20% / net vs blanket 20% | 6 / 5 / INR 13289.57 |

## Legal-baseline view (v3 metrics)

| Metric | Result |
|---|---|
| Beats the best margin-floor-LEGAL blanket depth (0 if none is legal) | 19 of 20 |
| Blanket 20% is floor-illegal in | 20 of 20 scenarios |
| Scenarios where the model-free upper bound exceeds blanket 20% (a legal play can beat it) | 15 |
| Of those, beaten by the planner | 14 |
| Valid runs; mean model calls per run; mean prompt tokens per run | 20; 4.0; 22953 |

## v4 metrics

| Metric | Result |
|---|---|
| Model turns per run: mean / median / max | 4.05 / 4.0 / 7 |
| Prompt tokens per run (mean); output + thinking tokens per run (mean) | 22953; 1738 |
| Beats blanket 20%, all valid | 14 of 20 |
| Beats blanket 20% against the ceiling (scenarios where a legal play can) | 14 of 15 |
| Net vs blanket 20%, raw / with a loss-making blanket counted as 0 | INR 22635.33 / INR 13297.54 |
| Turn-count distribution | {'3': 6, '4': 11, '6': 2, '7': 1} |

## By gap type

| Gap type | n | beats blanket |
|---|---|---|
| expiry_writeoff | 10 | 7 |
| online_sellby_breach | 10 | 7 |

## Per scenario

| id | outcome | mechanic | recovery | blanket 20% | upper bound | beats blanket | iterations |
|---|---|---|---|---|---|---|---|
| D01 | model_play | bundle | 736.32 | 318.66 | 911.21 | True | 1 |
| D02 | model_play | bundle | 955.29 | -130.11 | 1256.63 | True | 1 |
| D03 | model_play | bundle | 3759.89 | -3624.95 | 5704.64 | True | 1 |
| D04 | model_play | bundle | 1203.26 | -821.64 | 1580.19 | True | 1 |
| D05 | model_play | bundle | 1855.87 | 1010.07 | 2236.95 | True | 1 |
| D06 | model_play | bundle | 1897.63 | 4075.38 | 2475.48 | False | 1 |
| D07 | model_play | bundle | 1631.10 | 821.44 | 1626.43 | True | 1 |
| D08 | model_play | bundle | 2023.10 | 4800.00 | 2380.84 | False | 1 |
| D09 | model_play | bundle | 1745.37 | 2323.38 | 2372.91 | False | 1 |
| D10 | model_play | bundle | 5365.45 | -3886.77 | 8289.15 | True | 1 |
| D11 | model_play | transfer_plus_nudge | 1937.84 | 10643.37 | 3350.30 | False | 1 |
| D12 | model_play | bundle | 768.70 | 1404.03 | 814.30 | False | 1 |
| D13 | model_play | markdown | 902.83 | 845.21 | 902.83 | True | 1 |
| D14 | model_play | bundle | 4861.46 | 2900.86 | 4939.88 | True | 1 |
| D15 | model_play | bundle | 5618.00 | 847.20 | 7100.10 | True | 1 |
| D16 | model_play | bundle | 6163.18 | 4720.63 | 6198.77 | True | 1 |
| D17 | model_play | bundle | 3509.42 | 7959.30 | 3350.30 | False | 1 |
| D18 | model_play | markdown | 4256.32 | 2780.50 | 4173.60 | True | 1 |
| D19 | model_play | bundle | 6047.04 | 2604.74 | 6127.12 | True | 1 |
| D20 | model_play | markdown | 6114.24 | -874.32 | 6114.24 | True | 1 |
