# Loss analysis of sealed v2 and v3 (offline, no model call)

DEV material: the v4 dev set is built from these cases and tuned on; not an independent test. Runs read from `eval/raw/sealed_v2_2026-10-19/` and (read-only) `planner/markdown-option`'s `eval/raw/sealed_v3_2026-10-19/`. The v1-regression runs have no markdown baselines (v1 files) and are not used here.

Valid model plays analysed: 71 (v2 35, v3 36). Losses (recovery below the best allowed markdown, or captured < 0.9 of the upper bound): **27** (v2 14, v3 13).

## Causes

| cause | n | cases |
|---|---|---|
| bundle chosen below the oracle's best legal play (variant/partner/audience choice) | 13 | v2 S02, v2 S09, v2 S13, v2 S22, v2 S26, v3 S02, v3 S04, v3 S06, v3 S08, v3 S11, v3 S14, v3 S15, v3 S18 |
| other legal play below the upper bound (outlet_markdown) | 7 | v2 S04, v2 S08, v2 S14, v2 S18, v3 S01, v3 S05, v3 S09 |
| other legal play below the upper bound (transfer_plus_nudge) | 3 | v2 S03, v3 S10, v3 S19 |
| tolerance let a below-markdown play through | 3 | v2 S31, v2 S34, v2 S36 |
| other legal play below the upper bound (coupon) | 1 | v2 S29 |

## Offline replay of the gate on the recorded accepted plays

* Plays below the best allowed markdown by more than the OLD tolerance max(500, 5%): 0 (the gate was live, so the recorded plays had none).
* Plays that the NEW tolerance max(50, 2%) would have sent back: **2** of 71 (v2 S31, v2 S34), of 3 that were below the markdown at all.
* Rupees below the best markdown on those, total: INR 214.32; of which the new tolerance covers INR 135.90.

## Turns and latency

* Model turns per run: median 6, mean 6.06 (v2 6.06, v3 6.06).
* Latency p50: v2 41.5 s, v3 31.35 s. Latency vs turns correlation: 0.34.
* Losses average 6.04 turns vs 6.07 for non-losses.

## Not model losses

* Lost to blanket 20% where the oracle upper bound is also below it (blanket is floor-illegal and generously priced; no legal play can beat it): 20 (v2 S07, v2 S24, v2 S27, v2 S28, v2 S33, v3 S07, v3 S16, v3 S20, v3 S21, v3 S22, v3 S24, v3 S25, v3 S26, v3 S29, v3 S30, v3 S31, v3 S32, v3 S33, v3 S34, v3 S36).
* Ceiling scenarios (a legal play can beat blanket 20%) that the model missed: 2 (v2 S34, v3 S11).

## Every loss

| set | id | gap type | units | days | margin % | chosen | recovery | best allowed markdown | best legal non-markdown | upper bound | captured | gap to md | turns | latency s | cause |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| v2 | S02 | expiry_writeoff | 29 | 9 | 10.4 | bundle | 920.46 | 0.00 (None%) | 1053.57 (bundle) | 1053.57 | 0.87 | 0.00 | 7 | 44.6 | bundle chosen below the oracle's best legal play (variant/partner/audience choice) |
| v2 | S03 | expiry_writeoff | 18 | 11 | 11.4 | transfer_plus_nudge | 3232.62 | 0.00 (None%) | 3795.86 (bundle) | 3795.86 | 0.85 | 0.00 | 7 | 44.9 | other legal play below the upper bound (transfer_plus_nudge) |
| v2 | S04 | expiry_writeoff | 11 | 11 | 21.4 | outlet_markdown | 710.91 | 0.00 (None%) | 914.31 (bundle) | 914.31 | 0.78 | 0.00 | 4 | 18.8 | other legal play below the upper bound (outlet_markdown) |
| v2 | S08 | expiry_writeoff | 71 | 8 | 19.0 | outlet_markdown | 736.20 | 0.00 (None%) | 833.40 (bundle) | 833.40 | 0.88 | 0.00 | 7 | 35.8 | other legal play below the upper bound (outlet_markdown) |
| v2 | S09 | expiry_writeoff | 10 | 13 | 19.4 | bundle | 730.23 | 0.00 (None%) | 919.97 (bundle) | 919.97 | 0.79 | 0.00 | 8 | 31.8 | bundle chosen below the oracle's best legal play (variant/partner/audience choice) |
| v2 | S13 | expiry_writeoff | 92 | 5 | 17.6 | bundle | 2070.98 | 0.00 (None%) | 2348.48 (bundle) | 2348.48 | 0.88 | 0.00 | 7 | 44.6 | bundle chosen below the oracle's best legal play (variant/partner/audience choice) |
| v2 | S14 | expiry_writeoff | 71 | 7 | 19.0 | outlet_markdown | 664.43 | 0.00 (None%) | 752.08 (bundle) | 752.08 | 0.88 | 0.00 | 4 | 22.5 | other legal play below the upper bound (outlet_markdown) |
| v2 | S18 | expiry_writeoff | 11 | 11 | 21.4 | outlet_markdown | 710.91 | 0.00 (None%) | 983.32 (bundle) | 983.32 | 0.72 | 0.00 | 6 | 25.9 | other legal play below the upper bound (outlet_markdown) |
| v2 | S22 | online_sellby_breach | 15 | 12 | 21.9 | bundle | 2806.87 | 0.00 (10.0%) | 3816.52 (bundle) | 3816.52 | 0.74 | 0.00 | 6 | 30.1 | bundle chosen below the oracle's best legal play (variant/partner/audience choice) |
| v2 | S26 | online_sellby_breach | 26 | 11 | 13.2 | bundle | 1628.64 | 0.00 (None%) | 1813.29 (bundle) | 1813.29 | 0.90 | 0.00 | 5 | 64.1 | bundle chosen below the oracle's best legal play (variant/partner/audience choice) |
| v2 | S29 | online_sellby_breach | 208 | 4 | 19.0 | coupon | 1106.55 | 748.82 (10.0%) | 1252.58 (bundle) | 1252.58 | 0.88 | 0.00 | 6 | 43.0 | other legal play below the upper bound (coupon) |
| v2 | S31 | online_sellby_breach | 108 | 6 | 19.0 | bundle | 744.16 | 814.30 (10.0%) | 752.08 (bundle) | 814.30 | 0.91 | 70.14 | 4 | 44.7 | tolerance let a below-markdown play through |
| v2 | S34 | online_sellby_breach | 76 | 6 | 19.0 | bundle | 837.07 | 902.83 (10.0%) | 833.40 (bundle) | 902.83 | 0.93 | 65.76 | 7 | 43.8 | tolerance let a below-markdown play through |
| v2 | S36 | online_sellby_breach | 76 | 7 | 19.8 | bundle | 4861.46 | 4939.88 (10.0%) | 4726.19 (bundle) | 4939.88 | 0.98 | 78.42 | 6 | 41.7 | tolerance let a below-markdown play through |
| v3 | S01 | expiry_writeoff | 16 | 9 | 14.3 | outlet_markdown | 684.00 | 0.00 (None%) | 911.21 (bundle) | 911.21 | 0.75 | 0.00 | 4 | 28.7 | other legal play below the upper bound (outlet_markdown) |
| v3 | S02 | expiry_writeoff | 10 | 9 | 21.6 | bundle | 978.47 | 0.00 (None%) | 1256.63 (bundle) | 1256.63 | 0.78 | 0.00 | 5 | 26.0 | bundle chosen below the oracle's best legal play (variant/partner/audience choice) |
| v3 | S04 | expiry_writeoff | 41 | 11 | 16.0 | bundle | 3759.89 | 0.00 (None%) | 5704.64 (bundle) | 5704.64 | 0.66 | 0.00 | 7 | 40.8 | bundle chosen below the oracle's best legal play (variant/partner/audience choice) |
| v3 | S05 | expiry_writeoff | 12 | 12 | 23.6 | outlet_markdown | 945.29 | 0.00 (None%) | 1580.19 (bundle) | 1580.19 | 0.60 | 0.00 | 4 | 15.9 | other legal play below the upper bound (outlet_markdown) |
| v3 | S06 | expiry_writeoff | 46 | 4 | 16.2 | bundle | 1855.87 | 0.00 (None%) | 2236.95 (bundle) | 2236.95 | 0.83 | 0.00 | 7 | 34.1 | bundle chosen below the oracle's best legal play (variant/partner/audience choice) |
| v3 | S08 | expiry_writeoff | 84 | 7 | 10.1 | bundle | 1923.69 | 0.00 (None%) | 2475.48 (bundle) | 2475.48 | 0.78 | 0.00 | 6 | 30.4 | bundle chosen below the oracle's best legal play (variant/partner/audience choice) |
| v3 | S09 | expiry_writeoff | 67 | 3 | 23.1 | outlet_markdown | 1407.17 | 0.00 (None%) | 1626.43 (coupon) | 1626.43 | 0.87 | 0.00 | 4 | 23.9 | other legal play below the upper bound (outlet_markdown) |
| v3 | S10 | expiry_writeoff | 86 | 7 | 10.1 | transfer_plus_nudge | 1207.02 | 0.00 (None%) | 2380.84 (bundle) | 2380.84 | 0.51 | 0.00 | 8 | 37.3 | other legal play below the upper bound (transfer_plus_nudge) |
| v3 | S11 | expiry_writeoff | 73 | 8 | 20.2 | bundle | 1718.92 | 0.00 (None%) | 2372.91 (bundle) | 2372.91 | 0.72 | 0.00 | 7 | 37.5 | bundle chosen below the oracle's best legal play (variant/partner/audience choice) |
| v3 | S14 | online_sellby_breach | 51 | 11 | 17.1 | bundle | 5365.45 | 0.00 (None%) | 8289.15 (bundle) | 8289.15 | 0.65 | 0.00 | 8 | 41.9 | bundle chosen below the oracle's best legal play (variant/partner/audience choice) |
| v3 | S15 | online_sellby_breach | 20 | 12 | 14.7 | bundle | 800.31 | 0.00 (None%) | 956.18 (bundle) | 956.18 | 0.84 | 0.00 | 9 | 40.2 | bundle chosen below the oracle's best legal play (variant/partner/audience choice) |
| v3 | S18 | online_sellby_breach | 16 | 11 | 21.5 | bundle | 3124.17 | 226.67 (10.0%) | 3731.91 (bundle) | 3731.91 | 0.84 | 0.00 | 6 | 29.2 | bundle chosen below the oracle's best legal play (variant/partner/audience choice) |
| v3 | S19 | online_sellby_breach | 236 | 6 | 10.1 | transfer_plus_nudge | 1765.84 | 0.00 (None%) | 3350.30 (bundle) | 3350.30 | 0.53 | 0.00 | 4 | 36.7 | other legal play below the upper bound (transfer_plus_nudge) |
