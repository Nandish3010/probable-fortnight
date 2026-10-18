# Sealed decision-quality eval (2026-10-18)

Label: **measured**. Model gemini-3.5-flash, prompt v8, 10 valid scenarios of 10, concurrency 3, 1 run per scenario (plus one re-run of an INVALID run). Protocol: eval/sealed/PROTOCOL_v2.md section 5 (v1 regression, continuation of the 10 scenarios the USD 4 reserve rule left NOT RUN).

Recovery is the projected recovery under Taal's own estimator (recovered versus doing nothing) on a synthetic tenant, not a real-world outcome. A fallback play or no play counts as not beating either baseline.

| Metric | Result |
|---|---|
| **PRIMARY: beats blanket 20% markdown** | **9 of 10**; rupees by which it beats it where it does INR 30640.91 (net over all scenarios INR 17574.83) |
| Beats doing nothing | 10 of 10 |
| **HARD: guardrail violations reaching Approve (must be 0)** | **0** |
| Outcomes: model-authored play / deterministic fallback / no play | 10 / 0 / 0 |
| First proposal accepted by the gate; mean iterations | 10 of 10; 1 |
| Latency p50 / p95 (s) | 37.6 / 55.6 |
| Cost per scenario (USD) mean / max; total spend | 0.0872 / 0.1250; 0.8724 |
| Mechanic mix of accepted plays | bundle 9, markdown 1 |
| SECONDARY, estimator upper bound (not a best play): captured ratio median / p10 / min | 1.082 / 0.797 / 0.766 (n=10) |

The upper bound is the highest recovery among the candidates in the oracle's grid that pass every guardrail, scored by the same estimator. The estimator ignores discount depth and counts a bundle's full price per responding unit, so the bound favours a lowest-discount bundle; it is not an optimal or best-possible play.


## By gap type

| Gap type | n | beats blanket |
|---|---|---|
| online_sellby_breach | 10 | 9 |

## Per scenario

| id | outcome | mechanic | recovery | blanket 20% | upper bound | beats blanket | iterations |
|---|---|---|---|---|---|---|---|
| S27 | model_play | bundle | 4495.02 | 331.48 | 3423.39 | True | 1 |
| S28 | model_play | bundle | 2439.92 | -3979.95 | 3186.30 | True | 1 |
| S29 | model_play | bundle | 2330.40 | -563.77 | 1909.71 | True | 1 |
| S30 | model_play | bundle | 1827.53 | -2119.45 | 2283.79 | True | 1 |
| S31 | model_play | markdown | 20258.75 | 33324.83 | 16662.41 | False | 1 |
| S32 | model_play | bundle | 1320.08 | 932.76 | 1053.06 | True | 1 |
| S33 | model_play | bundle | 2454.24 | -832.44 | 2588.08 | True | 1 |
| S34 | model_play | bundle | 2934.24 | -433.20 | 3135.83 | True | 1 |
| S35 | model_play | bundle | 1738.42 | -869.56 | 2047.53 | True | 1 |
| S36 | model_play | bundle | 3082.17 | -484.76 | 2512.82 | True | 1 |
