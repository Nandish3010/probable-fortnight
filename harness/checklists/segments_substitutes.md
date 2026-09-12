---
component: segments_substitutes
title: Segments and substitutes
owner: D
spec_sections: ["5.2"]
tests: ["tests/sql/test_segments.py"]
---
# Segments and substitutes

## Deterministic (CI gate)
- [x] KMEANS k = 6 with a `segments` row per cluster
- [x] Every customer has a `segment_id`
- [x] Substitutes are same-category and at most top-5 per SKU
- [x] At chat time substitutes with zero stock at the node are filtered (`find_substitutes`)
- [x] `affinity` scores exist per customer x SKU from co-purchase

## Reviewer-verified
- [ ] Segment names are human-readable and written by hand
