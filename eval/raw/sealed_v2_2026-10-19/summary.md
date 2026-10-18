# Sealed decision-quality eval (2026-10-18)

Label: **measured**. Model gemini-3.5-flash, prompt v8, 35 valid scenarios of 36, concurrency 6, 1 run per scenario (plus one re-run of an INVALID run). Protocol: eval/sealed/PROTOCOL_v2.md.

Recovery is the projected recovery under Taal's own estimator (recovered versus doing nothing) on a synthetic tenant, not a real-world outcome. A fallback play or no play counts as not beating either baseline.

| Metric | Result |
|---|---|
| **PRIMARY: beats blanket 20% markdown** | **24 of 35**; rupees by which it beats it where it does INR 96105.07 (net over all scenarios INR 70277.20) |
| Beats doing nothing | 35 of 35 |
| **HARD: guardrail violations reaching Approve (must be 0)** | **0** |
| Outcomes: model-authored play / deterministic fallback / no play | 35 / 0 / 0 |
| First proposal accepted by the gate; mean iterations | 29 of 35; 1 |
| Latency p50 / p95 (s) | 41.5 / 64.4 |
| Cost per scenario (USD) mean / max; total spend | 0.0993 / 0.1573; 3.4752 |
| Mechanic mix of accepted plays | bundle 23, coupon 1, markdown 4, outlet_markdown 6, transfer_plus_nudge 1 |
| SECONDARY, estimator upper bound (not a best play): captured ratio median / p10 / min | 0.943 / 0.817 / 0.723 (n=35) |

The upper bound is the larger of the best allowed markdown play and the oracle's best legal non-markdown play (beats_markdown gate off), scored by the same est-v2 estimator; it is not an optimal or best-possible play.


## Markdown option (v2 metrics)

| Metric | Result |
|---|---|
| **Chooses a markdown where the best baseline is a markdown** | **4 of 7** |
| Net rupees vs blanket 20% markdown, all scenarios | INR 70277.20 |
| Net rupees vs the best blanket depth (10/20/35%), all scenarios | INR 18897.45 |
| Markdown chosen, all scenarios | 4 |
| Stratum feature: n / beats blanket 20% / net vs blanket 20% | 28 / 20 / INR 65225.83 |
| Stratum markdown_best: n / beats blanket 20% / net vs blanket 20% | 7 / 4 / INR 5051.37 |

## By gap type

| Gap type | n | beats blanket |
|---|---|---|
| expiry_writeoff | 18 | 14 |
| online_sellby_breach | 17 | 10 |

## Per scenario

| id | outcome | mechanic | recovery | blanket 20% | upper bound | beats blanket | iterations |
|---|---|---|---|---|---|---|---|
| S01 | model_play | bundle | 4693.74 | 3954.56 | 4429.54 | True | 1 |
| S02 | model_play | bundle | 920.46 | 212.83 | 1053.57 | True | 1 |
| S03 | model_play | transfer_plus_nudge | 3232.62 | -122.49 | 3795.86 | True | 1 |
| S04 | model_play | outlet_markdown | 710.91 | -53.50 | 914.31 | True | 1 |
| S05 | model_play | bundle | 2189.66 | -1503.12 | 2368.70 | True | 1 |
| S06 | model_play | bundle | 3135.66 | -33.66 | 3364.68 | True | 1 |
| S07 | model_play | outlet_markdown | 2219.04 | 2478.21 | 2456.61 | False | 1 |
| S08 | model_play | outlet_markdown | 736.20 | 921.36 | 833.40 | False | 1 |
| S09 | model_play | bundle | 730.23 | -255.10 | 919.97 | True | 1 |
| S10 | model_play | bundle | 4104.63 | -753.97 | 4129.69 | True | 1 |
| S11 | model_play | bundle | 2961.74 | -6492.53 | 3096.65 | True | 1 |
| S12 | model_play | outlet_markdown | 2326.97 | -814.25 | 2435.93 | True | 1 |
| S13 | model_play | bundle | 2070.98 | 2455.07 | 2348.48 | False | 1 |
| S14 | model_play | outlet_markdown | 664.43 | 876.91 | 752.08 | False | 1 |
| S15 | model_play | bundle | 6245.42 | -3190.06 | 6412.44 | True | 1 |
| S16 | model_play | bundle | 3405.82 | -570.36 | 3598.70 | True | 1 |
| S17 | model_play | bundle | 1955.72 | -3964.04 | 2020.38 | True | 1 |
| S18 | model_play | outlet_markdown | 710.91 | -182.98 | 983.32 | True | 1 |
| S19 | model_play | bundle | 3473.24 | 1603.68 | 3611.02 | True | 1 |
| S20 | model_play | bundle | 1286.12 | 527.20 | 1413.23 | True | 1 |
| S22 | model_play | bundle | 2806.87 | -12530.50 | 3816.52 | True | 1 |
| S23 | model_play | bundle | 3086.49 | -1821.66 | 3271.95 | True | 1 |
| S24 | model_play | bundle | 4579.12 | 6519.45 | 4760.12 | False | 1 |
| S25 | model_play | bundle | 6713.96 | -3361.25 | 6861.94 | True | 1 |
| S26 | model_play | bundle | 1628.64 | -278.56 | 1813.29 | True | 1 |
| S27 | model_play | bundle | 3434.76 | 11824.52 | 3571.39 | False | 1 |
| S28 | model_play | bundle | 2839.72 | 12007.97 | 2711.29 | False | 1 |
| S29 | model_play | coupon | 1106.55 | 1291.05 | 1252.58 | False | 1 |
| S30 | model_play | markdown | 10383.64 | 9661.18 | 10383.64 | True | 1 |
| S31 | model_play | bundle | 744.16 | 1404.03 | 814.30 | False | 1 |
| S32 | model_play | markdown | 11580.96 | 4472.79 | 11580.96 | True | 1 |
| S33 | model_play | markdown | 13951.14 | 18387.26 | 13951.14 | False | 1 |
| S34 | model_play | bundle | 837.07 | 845.21 | 902.83 | False | 1 |
| S35 | model_play | markdown | 1582.42 | 1218.15 | 1582.42 | True | 1 |
| S36 | model_play | bundle | 4861.46 | 2900.86 | 4939.88 | True | 1 |

## Excluded (INVALID or NOT RUN), reported and not scored

- S21: INVALID: call requested gemini-3.5-flash-lite
