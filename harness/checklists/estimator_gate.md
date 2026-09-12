---
component: estimator_gate
title: Estimator and gate
owner: B
spec_sections: ["2.5", "3.4", "17.5"]
tests: ["tests/unit"]
---
# Estimator and gate (`agents/gate`)

## Deterministic (CI gate)
- [ ] 100% branch coverage on the eight guardrail rules
- [x] Property test: margin after discount never below the category floor when the gate passes
- [x] Property test: holdout fraction respected within 1% on 10,000 hashed customers
- [x] `cite_or_drop` rejects a rationale number that is not in `citations`
- [x] Counterfactual arithmetic matches the spreadsheet fixture (`fixtures/estimator/`)
- [ ] Runtime invariant: an independent recomputation blocks a play write on mismatch (§17.5)
- [x] `online_sellby_date` unit tests cover the boundary day and non-food

## Reviewer-verified
- [x] Prior derivation is documented and weak by construction (low pseudo-count, disclosed)
- [ ] No LLM output reaches a rupee figure, an arm or a consent decision
