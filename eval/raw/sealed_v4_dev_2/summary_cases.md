# DEV round (dev set, tuned on; not an independent test)

v4 DEV ROUND 2 (dev set, tuned on; not an independent test): 20 cases (14 loss + 6 control); fixed 10, still lost 4, controls kept 6, newly broken/invalid 0 (none); mean model calls 3.95 (v3 6.06), mean prompt tokens 22579 (v3 51,097), p50/p95 latency 16.7/22.3 s (v3 31.3/42.3), violations 0, invalid 0, spend $0.6657.

Before = the recorded v2/v3 run of the same scenario (old code). Code head 76de6e2493 (working tree), prompt sha 285598fdb3fa, thinking {'planner_route': 'low', 'planner_final': 'low', 'customer': 'minimal'}.

| id | origin | role | mechanic | recovery before -> after | captured of upper bound | model turns | latency s | verdict | status |
|---|---|---|---|---|---|---|---|---|---|
| D01 | v3 S01 | loss | outlet_markdown -> bundle | 684.00 -> 787.43 (+103.43) | 0.75 -> 0.86 | 4 -> 4 | 28.7 -> 21.4 | VALID | STILL LOST |
| D02 | v3 S02 | loss | bundle -> bundle | 978.47 -> 978.47 (+0.00) | 0.78 -> 0.78 | 5 -> 4 | 26.0 -> 20.8 | VALID | STILL LOST |
| D03 | v3 S04 | loss | bundle -> bundle | 3759.89 -> 5758.01 (+1998.12) | 0.66 -> 1.01 | 7 -> 4 | 40.8 -> 21.0 | VALID | FIXED |
| D04 | v3 S05 | loss | outlet_markdown -> bundle | 945.29 -> 1133.91 (+188.62) | 0.60 -> 0.72 | 4 -> 4 | 15.9 -> 16.6 | VALID | STILL LOST |
| D05 | v3 S06 | loss | bundle -> bundle | 1855.87 -> 1855.87 (+0.00) | 0.83 -> 0.83 | 7 -> 4 | 34.1 -> 16.7 | VALID | STILL LOST |
| D06 | v3 S08 | loss | bundle -> bundle | 1923.69 -> 2556.93 (+633.24) | 0.78 -> 1.03 | 6 -> 3 | 30.4 -> 14.4 | VALID | FIXED |
| D07 | v3 S09 | loss | outlet_markdown -> bundle | 1407.17 -> 1572.50 (+165.33) | 0.87 -> 0.97 | 4 -> 3 | 23.9 -> 12.8 | VALID | FIXED |
| D08 | v3 S10 | loss | transfer_plus_nudge -> bundle | 1207.02 -> 2493.61 (+1286.59) | 0.51 -> 1.05 | 8 -> 3 | 37.3 -> 11.6 | VALID | FIXED |
| D09 | v3 S11 | loss | bundle -> bundle | 1718.92 -> 2311.60 (+592.68) | 0.72 -> 0.97 | 7 -> 4 | 37.5 -> 13.1 | VALID | FIXED |
| D10 | v3 S14 | loss | bundle -> bundle | 5365.45 -> 8426.64 (+3061.19) | 0.65 -> 1.02 | 8 -> 4 | 41.9 -> 15.9 | VALID | FIXED |
| D11 | v3 S19 | loss | transfer_plus_nudge -> bundle | 1765.84 -> 3509.42 (+1743.58) | 0.53 -> 1.05 | 4 -> 3 | 36.7 -> 14.3 | VALID | FIXED |
| D12 | v2 S31 | loss | bundle -> markdown | 744.16 -> 814.30 (+70.14) | 0.91 -> 1.0 | 4 -> 4 | 44.7 -> 17.2 | VALID | FIXED |
| D13 | v2 S34 | loss | bundle -> markdown | 837.07 -> 902.83 (+65.76) | 0.93 -> 1.0 | 7 -> 5 | 43.8 -> 22.1 | VALID | FIXED |
| D14 | v2 S36 | loss | bundle -> markdown | 4861.46 -> 4939.88 (+78.42) | 0.98 -> 1.0 | 6 -> 4 | 41.7 -> 17.8 | VALID | FIXED |
| D15 | v3 S03 | control | bundle -> bundle | 7040.10 -> 7040.10 (+0.00) | 0.99 -> 0.99 | 5 -> 4 | 33.1 -> 17.0 | VALID | kept |
| D16 | v3 S17 | control | bundle -> bundle | 6300.58 -> 6300.58 (+0.00) | 1.02 -> 1.02 | 8 -> 4 | 43.5 -> 16.1 | VALID | kept |
| D17 | v3 S20 | control | bundle -> bundle | 3509.42 -> 3509.42 (+0.00) | 1.05 -> 1.05 | 10 -> 3 | 43.6 -> 12.5 | VALID | kept |
| D18 | v3 S23 | control | markdown -> markdown | 4173.60 -> 4256.32 (+82.72) | 1.00 -> 1.02 | 5 -> 6 | 28.6 -> 25.9 | VALID | kept |
| D19 | v3 S28 | control | markdown -> markdown | 6127.12 -> 6127.12 (+0.00) | 1.00 -> 1.0 | 5 -> 6 | 29.3 -> 22.1 | VALID | kept |
| D20 | v3 S35 | control | markdown -> markdown | 6114.24 -> 6114.24 (+0.00) | 1.00 -> 1.0 | 5 -> 3 | 22.6 -> 15.9 | VALID | kept |

