# Sealed decision-quality eval (2026-10-18)

Label: **measured**. Model gemini-3.5-flash, prompt v7, 36 valid scenarios of 36, concurrency 4, 1 run per scenario (plus one re-run of an INVALID run). Protocol: eval/sealed/PROTOCOL.md.

Recovery is the projected recovery under Taal's own estimator (recovered versus doing nothing) on a synthetic tenant, not a real-world outcome. A fallback play or no play counts as not beating either baseline.

| Metric | Result |
|---|---|
| **PRIMARY: beats blanket 20% markdown** | **29 of 36**; rupees by which it beats it where it does INR 68846.22 (net over all scenarios INR 13172.82) |
| Beats doing nothing | 36 of 36 |
| **HARD: guardrail violations reaching Approve (must be 0)** | **0** |
| Outcomes: model-authored play / deterministic fallback / no play | 36 / 0 / 0 |
| First proposal accepted by the gate; mean iterations | 35 of 36; 1 |
| Latency p50 / p95 (s) | 23.4 / 38.5 |
| Cost per scenario (USD) mean / max; total spend | 0.0802 / 0.1304; 2.8863 |
| Mechanic mix of accepted plays | bundle 23, transfer_plus_nudge 12, usual_order_addon 1 |
| SECONDARY, estimator upper bound (not a best play): captured ratio median / p10 / min | 0.747 / 0.543 / 0.335 (n=36) |

The upper bound is the highest recovery among the candidates in the oracle's grid that pass every guardrail, scored by the same estimator. The estimator ignores discount depth and counts a bundle's full price per responding unit, so the bound favours a lowest-discount bundle; it is not an optimal or best-possible play.

## By gap type

| Gap type | n | beats blanket |
|---|---|---|
| expiry_writeoff | 18 | 14 |
| online_sellby_breach | 18 | 15 |

## Per scenario

| id | outcome | mechanic | recovery | blanket 20% | upper bound | beats blanket | iterations |
|---|---|---|---|---|---|---|---|
| S01 | model_play | bundle | 2419.47 | 1776.55 | 3265.19 | True | 1 |
| S02 | model_play | bundle | 2718.77 | -644.81 | 3085.18 | True | 1 |
| S03 | model_play | bundle | 787.85 | 47.43 | 894.22 | True | 1 |
| S04 | model_play | bundle | 2769.72 | 1431.98 | 4139.55 | True | 1 |
| S05 | model_play | bundle | 1020.60 | 521.14 | 1353.75 | True | 1 |
| S06 | model_play | bundle | 678.94 | 268.50 | 812.41 | True | 1 |
| S07 | model_play | bundle | 4653.62 | 13752.25 | 9414.31 | False | 1 |
| S08 | model_play | bundle | 7033.25 | 7289.40 | 10242.40 | False | 1 |
| S09 | model_play | bundle | 7198.13 | 11695.30 | 8887.19 | False | 1 |
| S10 | model_play | bundle | 5350.08 | 13229.25 | 12070.73 | False | 1 |
| S11 | model_play | bundle | 3329.40 | 1821.32 | 3431.15 | True | 1 |
| S12 | model_play | bundle | 1088.88 | 948.22 | 1613.91 | True | 1 |
| S13 | model_play | bundle | 3364.77 | -1118.09 | 3690.30 | True | 1 |
| S14 | model_play | bundle | 2413.36 | 608.92 | 2889.86 | True | 1 |
| S15 | model_play | bundle | 3314.07 | 1521.60 | 3851.84 | True | 1 |
| S16 | model_play | bundle | 716.95 | 395.52 | 800.90 | True | 1 |
| S17 | model_play | bundle | 1686.41 | -8.67 | 1746.12 | True | 1 |
| S18 | model_play | bundle | 2183.77 | 712.80 | 2660.27 | True | 1 |
| S19 | model_play | bundle | 1003.74 | 670.53 | 1135.78 | True | 1 |
| S20 | model_play | usual_order_addon | 1556.08 | 762.75 | 1684.30 | True | 1 |
| S21 | model_play | transfer_plus_nudge | 538.00 | -3397.38 | 977.60 | True | 1 |
| S22 | model_play | transfer_plus_nudge | 1943.74 | -5912.07 | 2682.57 | True | 1 |
| S23 | model_play | transfer_plus_nudge | 877.25 | 144.81 | 1199.36 | True | 1 |
| S24 | model_play | transfer_plus_nudge | 5099.97 | -4857.98 | 5863.55 | True | 1 |
| S25 | model_play | transfer_plus_nudge | 1009.95 | 674.03 | 1530.81 | True | 1 |
| S26 | model_play | transfer_plus_nudge | 2568.65 | 8495.90 | 4292.78 | False | 1 |
| S27 | model_play | transfer_plus_nudge | 2477.59 | 331.48 | 3423.39 | True | 1 |
| S28 | model_play | transfer_plus_nudge | 1787.10 | -3979.95 | 3186.30 | True | 1 |
| S29 | model_play | transfer_plus_nudge | 1267.24 | -563.77 | 1909.71 | True | 1 |
| S30 | model_play | transfer_plus_nudge | 1222.80 | -2119.45 | 2283.79 | True | 1 |
| S31 | model_play | bundle | 5585.50 | 33324.83 | 16662.41 | False | 1 |
| S32 | model_play | transfer_plus_nudge | 657.06 | 932.76 | 1053.06 | False | 1 |
| S33 | model_play | bundle | 2578.21 | -832.44 | 2588.08 | True | 1 |
| S34 | model_play | bundle | 2818.44 | -433.20 | 3135.83 | True | 1 |
| S35 | model_play | transfer_plus_nudge | 1419.84 | -869.56 | 2047.53 | True | 1 |
| S36 | model_play | bundle | 2168.76 | -484.76 | 2512.82 | True | 1 |
