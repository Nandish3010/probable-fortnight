---
component: docs_submission
title: Docs and submission
owner: A
spec_sections: ["11a", "12", "13"]
tests: ["make docs"]
---
# Docs and submission

## Deterministic (CI gate)
- [x] README lint: title first, "Judge quick-start" within the first 40 lines, links resolve, no vendor names
- [x] Screenshots referenced from the README exist under `docs/screenshots/`
- [ ] Video file length <= 2:45
- [ ] Links public (fetched in an incognito-like check)
- [ ] Deck PDF opens; documentation PDF exists
- [x] `DATA_LICENSES.md` present; no third-party raw data in the tree
- [x] Evaluation table filled from `eval/` at freeze, never typed by hand

## Reviewer-verified
- [ ] Slide 2 and the closing card carry the same number as Outcomes
- [x] "What is real, what is simulated" box present in README and deck
