# DEV round (dev set, tuned on; not an independent test)

v4 DEV ROUND 1 (dev set, tuned on; not an independent test): 20 cases (14 loss + 6 control); fixed 2, still lost 12, controls kept 4, newly broken/invalid 2 (D15, D16); mean model calls 4.05 (v3 6.06), mean prompt tokens 22953 (v3 51,097), p50/p95 latency 14.5/26.4 s (v3 31.3/42.3), violations 0, invalid 0, spend $0.6908.

Before = the recorded v2/v3 run of the same scenario (old code). Code head 76de6e2493 (working tree), prompt sha c3447e95f9ce, thinking {'planner_route': 'low', 'planner_final': 'low', 'customer': 'minimal'}.

| id | origin | role | mechanic | recovery before -> after | captured of upper bound | model turns | latency s | verdict | status |
|---|---|---|---|---|---|---|---|---|---|
| D01 | v3 S01 | loss | outlet_markdown -> bundle | 684.00 -> 736.32 (+52.32) | 0.75 -> 0.81 | 4 -> 3 | 28.7 -> 11.3 | VALID | STILL LOST |
| D02 | v3 S02 | loss | bundle -> bundle | 978.47 -> 955.29 (-23.18) | 0.78 -> 0.76 | 5 -> 4 | 26.0 -> 16.0 | VALID | STILL LOST |
| D03 | v3 S04 | loss | bundle -> bundle | 3759.89 -> 3759.89 (+0.00) | 0.66 -> 0.66 | 7 -> 4 | 40.8 -> 12.8 | VALID | STILL LOST |
| D04 | v3 S05 | loss | outlet_markdown -> bundle | 945.29 -> 1203.26 (+257.97) | 0.60 -> 0.76 | 4 -> 4 | 15.9 -> 14.1 | VALID | STILL LOST |
| D05 | v3 S06 | loss | bundle -> bundle | 1855.87 -> 1855.87 (+0.00) | 0.83 -> 0.83 | 7 -> 4 | 34.1 -> 12.6 | VALID | STILL LOST |
| D06 | v3 S08 | loss | bundle -> bundle | 1923.69 -> 1897.63 (-26.06) | 0.78 -> 0.77 | 6 -> 3 | 30.4 -> 11.1 | VALID | STILL LOST |
| D07 | v3 S09 | loss | outlet_markdown -> bundle | 1407.17 -> 1631.10 (+223.93) | 0.87 -> 1.0 | 4 -> 4 | 23.9 -> 14.6 | VALID | FIXED |
| D08 | v3 S10 | loss | transfer_plus_nudge -> bundle | 1207.02 -> 2023.10 (+816.08) | 0.51 -> 0.85 | 8 -> 4 | 37.3 -> 16.1 | VALID | STILL LOST |
| D09 | v3 S11 | loss | bundle -> bundle | 1718.92 -> 1745.37 (+26.45) | 0.72 -> 0.74 | 7 -> 4 | 37.5 -> 15.8 | VALID | STILL LOST |
| D10 | v3 S14 | loss | bundle -> bundle | 5365.45 -> 5365.45 (+0.00) | 0.65 -> 0.65 | 8 -> 4 | 41.9 -> 17.1 | VALID | STILL LOST |
| D11 | v3 S19 | loss | transfer_plus_nudge -> transfer_plus_nudge | 1765.84 -> 1937.84 (+172.00) | 0.53 -> 0.58 | 4 -> 3 | 36.7 -> 13.8 | VALID | STILL LOST |
| D12 | v2 S31 | loss | bundle -> bundle | 744.16 -> 768.70 (+24.54) | 0.91 -> 0.94 | 4 -> 6 | 44.7 -> 19.4 | VALID | STILL LOST |
| D13 | v2 S34 | loss | bundle -> markdown | 837.07 -> 902.83 (+65.76) | 0.93 -> 1.0 | 7 -> 4 | 43.8 -> 13.7 | VALID | FIXED |
| D14 | v2 S36 | loss | bundle -> bundle | 4861.46 -> 4861.46 (+0.00) | 0.98 -> 0.98 | 6 -> 3 | 41.7 -> 13.4 | VALID | STILL LOST |
| D15 | v3 S03 | control | bundle -> bundle | 7040.10 -> 5618.00 (-1422.10) | 0.99 -> 0.79 | 5 -> 3 | 33.1 -> 14.4 | VALID | NEWLY BROKEN |
| D16 | v3 S17 | control | bundle -> bundle | 6300.58 -> 6163.18 (-137.40) | 1.02 -> 0.99 | 8 -> 3 | 43.5 -> 12.6 | VALID | NEWLY BROKEN |
| D17 | v3 S20 | control | bundle -> bundle | 3509.42 -> 3509.42 (+0.00) | 1.05 -> 1.05 | 10 -> 4 | 43.6 -> 20.6 | VALID | kept |
| D18 | v3 S23 | control | markdown -> markdown | 4173.60 -> 4256.32 (+82.72) | 1.00 -> 1.02 | 5 -> 7 | 28.6 -> 26.2 | VALID | kept |
| D19 | v3 S28 | control | markdown -> bundle | 6127.12 -> 6047.04 (-80.08) | 1.00 -> 0.99 | 5 -> 6 | 29.3 -> 29.8 | VALID | kept |
| D20 | v3 S35 | control | markdown -> markdown | 6114.24 -> 6114.24 (+0.00) | 1.00 -> 1.0 | 5 -> 4 | 22.6 -> 16.5 | VALID | kept |

