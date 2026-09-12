---
component: generator
title: Synthetic generator
owner: D
spec_sections: ["3.2", "3.3"]
tests: ["tests/unit/test_generator.py", "tests/sql"]
---
# Synthetic generator (`data/generator`)

Run: `make generate` (`python -m data.generator --out $TAAL_DATA_DIR --seed 20260912`).

## Deterministic (CI gate)
- [x] Seeded run is byte-identical twice (hash of every output file)
- [x] Row counts within spec: ~300 SKUs, 10 nodes + 6 outlets, ~4,000 customers
- [x] `online_sellby_date <= expiry_date` for every food batch row
- [x] No pet SKUs anywhere in the catalogue
- [x] Planted situations present, asserted by id: chips lot 6 days from online sell-by at DS-07; Diwali stockout risk at two nodes; slow mover at outlets; premium tea gap
- [x] Consent table covers every customer
- [x] Daily series built by the stated rule (weekly totals, day-of-week profile, fixed node shares plus noise)

## Reviewer-verified
- [ ] Planted situations match the demo script (§9 shots 3-5, 10)
- [x] `DATA_LICENSES.md` names every source and no raw third-party data is in the tree
