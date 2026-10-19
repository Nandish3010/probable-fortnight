# DEV round (dev set, tuned on; not an independent test)

v4 DEV ROUND 3 (dev set, tuned on; not an independent test): 20 cases (14 loss + 6 control); fixed 8, still lost 6, controls kept 6, newly broken/invalid 0 (none); mean model calls 4.05 (v3 6.06), mean prompt tokens 21040 (v3 51,097), p50/p95 latency 20.6/26.3 s (v3 31.3/42.3), violations 0, invalid 0, spend $0.5023.

Before = the recorded v2/v3 run of the same scenario (old code). Code head 76de6e2493 (working tree), prompt sha 285598fdb3fa, thinking {'planner_route': 'minimal', 'planner_final': 'low', 'customer': 'minimal'}.

| id | origin | role | mechanic | recovery before -> after | captured of upper bound | model turns | latency s | verdict | status |
|---|---|---|---|---|---|---|---|---|---|
| D01 | v3 S01 | loss | outlet_markdown -> bundle | 684.00 -> 767.27 (+83.27) | 0.75 -> 0.84 | 4 -> 4 | 28.7 -> 25.7 | VALID | STILL LOST |
| D02 | v3 S02 | loss | bundle -> bundle | 978.47 -> 978.47 (+0.00) | 0.78 -> 0.78 | 5 -> 4 | 26.0 -> 24.5 | VALID | STILL LOST |
| D03 | v3 S04 | loss | bundle -> bundle | 3759.89 -> 5758.01 (+1998.12) | 0.66 -> 1.01 | 7 -> 4 | 40.8 -> 24.9 | VALID | FIXED |
| D04 | v3 S05 | loss | outlet_markdown -> bundle | 945.29 -> 1133.91 (+188.62) | 0.60 -> 0.72 | 4 -> 4 | 15.9 -> 18.8 | VALID | STILL LOST |
| D05 | v3 S06 | loss | bundle -> bundle | 1855.87 -> 2094.39 (+238.52) | 0.83 -> 0.94 | 7 -> 4 | 34.1 -> 19.0 | VALID | FIXED |
| D06 | v3 S08 | loss | bundle -> bundle | 1923.69 -> 1923.69 (+0.00) | 0.78 -> 0.78 | 6 -> 4 | 30.4 -> 16.3 | VALID | STILL LOST |
| D07 | v3 S09 | loss | outlet_markdown -> bundle | 1407.17 -> 1572.23 (+165.06) | 0.87 -> 0.97 | 4 -> 4 | 23.9 -> 12.3 | VALID | FIXED |
| D08 | v3 S10 | loss | transfer_plus_nudge -> bundle | 1207.02 -> 2509.42 (+1302.40) | 0.51 -> 1.05 | 8 -> 4 | 37.3 -> 19.6 | VALID | FIXED |
| D09 | v3 S11 | loss | bundle -> bundle | 1718.92 -> 2276.34 (+557.42) | 0.72 -> 0.96 | 7 -> 4 | 37.5 -> 20.2 | VALID | FIXED |
| D10 | v3 S14 | loss | bundle -> bundle | 5365.45 -> 8426.64 (+3061.19) | 0.65 -> 1.02 | 8 -> 4 | 41.9 -> 21.1 | VALID | FIXED |
| D11 | v3 S19 | loss | transfer_plus_nudge -> bundle | 1765.84 -> 3371.47 (+1605.63) | 0.53 -> 1.01 | 4 -> 3 | 36.7 -> 14.7 | VALID | FIXED |
| D12 | v2 S31 | loss | bundle -> bundle | 744.16 -> 768.70 (+24.54) | 0.91 -> 0.94 | 4 -> 5 | 44.7 -> 33.2 | VALID | STILL LOST |
| D13 | v2 S34 | loss | bundle -> markdown | 837.07 -> 902.83 (+65.76) | 0.93 -> 1.0 | 7 -> 4 | 43.8 -> 24.9 | VALID | FIXED |
| D14 | v2 S36 | loss | bundle -> bundle | 4861.46 -> 4861.46 (+0.00) | 0.98 -> 0.98 | 6 -> 4 | 41.7 -> 26.0 | VALID | STILL LOST |
| D15 | v3 S03 | control | bundle -> bundle | 7040.10 -> 7040.10 (+0.00) | 0.99 -> 0.99 | 5 -> 4 | 33.1 -> 25.7 | VALID | kept |
| D16 | v3 S17 | control | bundle -> bundle | 6300.58 -> 6300.58 (+0.00) | 1.02 -> 1.02 | 8 -> 4 | 43.5 -> 22.1 | VALID | kept |
| D17 | v3 S20 | control | bundle -> bundle | 3509.42 -> 3509.42 (+0.00) | 1.05 -> 1.05 | 10 -> 4 | 43.6 -> 22.8 | VALID | kept |
| D18 | v3 S23 | control | markdown -> markdown | 4173.60 -> 4173.60 (+0.00) | 1.00 -> 1.0 | 5 -> 4 | 28.6 -> 13.5 | VALID | kept |
| D19 | v3 S28 | control | markdown -> markdown | 6127.12 -> 6127.12 (+0.00) | 1.00 -> 1.0 | 5 -> 4 | 29.3 -> 18.0 | VALID | kept |
| D20 | v3 S35 | control | markdown -> markdown | 6114.24 -> 6114.24 (+0.00) | 1.00 -> 1.0 | 5 -> 5 | 22.6 -> 16.2 | VALID | kept |

