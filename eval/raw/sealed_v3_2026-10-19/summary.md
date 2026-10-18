# Sealed decision-quality eval (2026-10-18)

Label: **measured**. Model gemini-3.5-flash, prompt v9, 36 valid scenarios of 36, concurrency 3, 1 run per scenario (plus one re-run of an INVALID run). Protocol: eval/sealed/PROTOCOL_v3.md.

Recovery is the projected recovery under Taal's own estimator (recovered versus doing nothing) on a synthetic tenant, not a real-world outcome. A fallback play or no play counts as not beating either baseline.

| Metric | Result |
|---|---|
| **PRIMARY: beats blanket 20% markdown** | **17 of 36**; rupees by which it beats it where it does INR 56833.71 (net over all scenarios INR -10319.64) |
| Beats doing nothing | 36 of 36 |
| **HARD: guardrail violations reaching Approve (must be 0)** | **0** |
| Outcomes: model-authored play / deterministic fallback / no play | 36 / 0 / 0 |
| First proposal accepted by the gate; mean iterations | 32 of 36; 1 |
| Latency p50 / p95 (s) | 31.3 / 42.3 |
| Cost per scenario (USD) mean / max; total spend | 0.0936 / 0.1346; 3.3712 |
| Mechanic mix of accepted plays | bundle 16, markdown 14, outlet_markdown 4, transfer_plus_nudge 2 |
| SECONDARY, estimator upper bound (not a best play): captured ratio median / p10 / min | 0.998 / 0.653 / 0.507 (n=36) |

The upper bound is the larger of the best allowed markdown play and the oracle's best legal non-markdown play (beats_markdown gate off), scored by the same est-v2 estimator; it is not an optimal or best-possible play.


## Markdown option (v2 metrics)

| Metric | Result |
|---|---|
| **Chooses a markdown where the best baseline is a markdown** | **14 of 15** |
| Net rupees vs blanket 20% markdown, all scenarios | INR -10319.64 |
| Net rupees vs the best blanket depth (10/20/35%), all scenarios | INR -89529.64 |
| Markdown chosen, all scenarios | 14 |
| Stratum feature: n / beats blanket 20% / net vs blanket 20% | 21 / 13 / INR 17849.59 |
| Stratum markdown_best: n / beats blanket 20% / net vs blanket 20% | 15 / 4 / INR -28169.23 |

## By gap type

| Gap type | n | beats blanket |
|---|---|---|
| expiry_writeoff | 12 | 8 |
| online_sellby_breach | 24 | 9 |

## Per scenario

| id | outcome | mechanic | recovery | blanket 20% | upper bound | beats blanket | iterations |
|---|---|---|---|---|---|---|---|
| S01 | model_play | outlet_markdown | 684.00 | 318.66 | 911.21 | True | 1 |
| S02 | model_play | bundle | 978.47 | -130.11 | 1256.63 | True | 1 |
| S03 | model_play | bundle | 7040.10 | 847.20 | 7100.10 | True | 1 |
| S04 | model_play | bundle | 3759.89 | -3624.95 | 5704.64 | True | 1 |
| S05 | model_play | outlet_markdown | 945.29 | -821.64 | 1580.19 | True | 1 |
| S06 | model_play | bundle | 1855.87 | 1010.07 | 2236.95 | True | 1 |
| S07 | model_play | bundle | 5162.92 | 7089.07 | 5616.14 | False | 1 |
| S08 | model_play | bundle | 1923.69 | 4075.38 | 2475.48 | False | 1 |
| S09 | model_play | outlet_markdown | 1407.17 | 821.44 | 1626.43 | True | 1 |
| S10 | model_play | transfer_plus_nudge | 1207.02 | 4800.00 | 2380.84 | False | 1 |
| S11 | model_play | bundle | 1718.92 | 2323.38 | 2372.91 | False | 1 |
| S12 | model_play | outlet_markdown | 1506.78 | 751.05 | 1626.43 | True | 1 |
| S13 | model_play | bundle | 4430.70 | -1648.54 | 4596.14 | True | 1 |
| S14 | model_play | bundle | 5365.45 | -3886.77 | 8289.15 | True | 1 |
| S15 | model_play | bundle | 800.31 | -426.44 | 956.18 | True | 1 |
| S16 | model_play | bundle | 8203.54 | 9969.91 | 8229.41 | False | 1 |
| S17 | model_play | bundle | 6300.58 | 4720.63 | 6198.77 | True | 1 |
| S18 | model_play | bundle | 3124.17 | -2631.30 | 3731.91 | True | 1 |
| S19 | model_play | transfer_plus_nudge | 1765.84 | 10643.37 | 3350.30 | False | 1 |
| S20 | model_play | bundle | 3509.42 | 7959.30 | 3350.30 | False | 1 |
| S21 | model_play | bundle | 3461.75 | 5142.58 | 3350.30 | False | 1 |
| S22 | model_play | markdown | 9616.98 | 15902.42 | 9616.98 | False | 1 |
| S23 | model_play | markdown | 4173.60 | 2780.50 | 4173.60 | True | 1 |
| S24 | model_play | markdown | 3317.02 | 3926.08 | 3317.02 | False | 1 |
| S25 | model_play | markdown | 14434.66 | 15904.49 | 14434.66 | False | 1 |
| S26 | model_play | markdown | 8304.77 | 12709.47 | 8304.77 | False | 1 |
| S27 | model_play | markdown | 6201.03 | 4170.84 | 6201.03 | True | 1 |
| S28 | model_play | markdown | 6127.12 | 2604.74 | 6127.12 | True | 1 |
| S29 | model_play | markdown | 9290.40 | 15363.14 | 9290.40 | False | 1 |
| S30 | model_play | bundle | 6450.28 | 10599.16 | 6409.69 | False | 1 |
| S31 | model_play | markdown | 9179.41 | 15176.71 | 9179.41 | False | 1 |
| S32 | model_play | markdown | 2873.29 | 4155.44 | 2873.29 | False | 1 |
| S33 | model_play | markdown | 13076.14 | 15598.80 | 13076.14 | False | 1 |
| S34 | model_play | markdown | 7496.02 | 12393.95 | 7496.02 | False | 1 |
| S35 | model_play | markdown | 6114.24 | -874.32 | 6114.24 | True | 1 |
| S36 | model_play | markdown | 6851.59 | 11264.36 | 6851.59 | False | 1 |
