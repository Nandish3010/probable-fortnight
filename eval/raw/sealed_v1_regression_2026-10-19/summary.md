# Sealed decision-quality eval (2026-10-18)

Label: **measured**. Model gemini-3.5-flash, prompt v8, 25 valid scenarios of 36, concurrency 6, 1 run per scenario (plus one re-run of an INVALID run). Protocol: eval/sealed/PROTOCOL_v2.md section 5 (v1 regression).

Recovery is the projected recovery under Taal's own estimator (recovered versus doing nothing) on a synthetic tenant, not a real-world outcome. A fallback play or no play counts as not beating either baseline.

| Metric | Result |
|---|---|
| **PRIMARY: beats blanket 20% markdown** | **21 of 25**; rupees by which it beats it where it does INR 53169.36 (net over all scenarios INR 32902.23) |
| Beats doing nothing | 25 of 25 |
| **HARD: guardrail violations reaching Approve (must be 0)** | **0** |
| Outcomes: model-authored play / deterministic fallback / no play | 25 / 0 / 0 |
| First proposal accepted by the gate; mean iterations | 24 of 25; 1 |
| Latency p50 / p95 (s) | 28.2 / 39.3 |
| Cost per scenario (USD) mean / max; total spend | 0.0881 / 0.1338; 2.2030 |
| Mechanic mix of accepted plays | bundle 15, coupon 3, outlet_markdown 7 |
| SECONDARY, estimator upper bound (not a best play): captured ratio median / p10 / min | 0.880 / 0.743 / 0.614 (n=25) |

The upper bound is the highest recovery among the candidates in the oracle's grid that pass every guardrail, scored by the same estimator. The estimator ignores discount depth and counts a bundle's full price per responding unit, so the bound favours a lowest-discount bundle; it is not an optimal or best-possible play.


## By gap type

| Gap type | n | beats blanket |
|---|---|---|
| expiry_writeoff | 17 | 14 |
| online_sellby_breach | 8 | 7 |

## Per scenario

| id | outcome | mechanic | recovery | blanket 20% | upper bound | beats blanket | iterations |
|---|---|---|---|---|---|---|---|
| S01 | model_play | bundle | 3436.02 | 1776.55 | 3265.19 | True | 1 |
| S02 | model_play | bundle | 2631.53 | -644.81 | 3085.18 | True | 1 |
| S04 | model_play | outlet_markdown | 3643.02 | 1431.98 | 4139.55 | True | 1 |
| S05 | model_play | bundle | 1099.17 | 521.14 | 1353.75 | True | 1 |
| S06 | model_play | outlet_markdown | 619.87 | 268.50 | 812.41 | True | 1 |
| S07 | model_play | outlet_markdown | 6867.10 | 13752.25 | 9414.31 | False | 1 |
| S08 | model_play | bundle | 8647.05 | 7289.40 | 10242.40 | True | 1 |
| S09 | model_play | outlet_markdown | 9652.49 | 11695.30 | 8887.19 | False | 1 |
| S10 | model_play | coupon | 7416.00 | 13229.25 | 12070.73 | False | 1 |
| S11 | model_play | bundle | 4307.00 | 1821.32 | 3431.15 | True | 1 |
| S12 | model_play | outlet_markdown | 1803.20 | 948.22 | 1613.91 | True | 1 |
| S13 | model_play | bundle | 3456.63 | -1118.09 | 3690.30 | True | 1 |
| S14 | model_play | outlet_markdown | 2456.50 | 608.92 | 2889.86 | True | 1 |
| S15 | model_play | outlet_markdown | 3114.26 | 1521.60 | 3851.84 | True | 1 |
| S16 | model_play | bundle | 715.08 | 395.52 | 800.90 | True | 1 |
| S17 | model_play | bundle | 1383.96 | -8.67 | 1746.12 | True | 1 |
| S18 | model_play | bundle | 2183.83 | 712.80 | 2660.27 | True | 1 |
| S19 | model_play | bundle | 1449.94 | 670.53 | 1135.78 | True | 1 |
| S20 | model_play | bundle | 2051.14 | 762.75 | 1684.30 | True | 1 |
| S21 | model_play | bundle | 795.36 | -3397.38 | 977.60 | True | 1 |
| S22 | model_play | bundle | 3202.79 | -5912.07 | 2682.57 | True | 1 |
| S23 | model_play | bundle | 1499.72 | 144.81 | 1199.36 | True | 1 |
| S24 | model_play | bundle | 6466.34 | -4857.98 | 5863.55 | True | 1 |
| S25 | model_play | coupon | 1816.02 | 674.03 | 1530.81 | True | 1 |
| S26 | model_play | coupon | 2969.98 | 8495.90 | 4292.78 | False | 1 |

## Excluded (INVALID or NOT RUN), reported and not scored

- S03: INVALID: call requested gemini-3.5-flash-lite
- S27: NOT_RUN: spend cap: spent 2.2932 + reserved 1.50 + reserve 0.3 would pass 4.0
- S28: NOT_RUN: spend cap: spent 2.2932 + reserved 1.50 + reserve 0.3 would pass 4.0
- S29: NOT_RUN: spend cap: spent 2.2932 + reserved 1.50 + reserve 0.3 would pass 4.0
- S30: NOT_RUN: spend cap: spent 2.2932 + reserved 1.50 + reserve 0.3 would pass 4.0
- S31: NOT_RUN: spend cap: spent 2.2932 + reserved 1.50 + reserve 0.3 would pass 4.0
- S32: NOT_RUN: spend cap: spent 2.2932 + reserved 1.50 + reserve 0.3 would pass 4.0
- S33: NOT_RUN: spend cap: spent 2.2932 + reserved 1.50 + reserve 0.3 would pass 4.0
- S34: NOT_RUN: spend cap: spent 2.2932 + reserved 1.50 + reserve 0.3 would pass 4.0
- S35: NOT_RUN: spend cap: spent 2.2932 + reserved 1.50 + reserve 0.3 would pass 4.0
- S36: NOT_RUN: spend cap: spent 2.2932 + reserved 1.50 + reserve 0.3 would pass 4.0
