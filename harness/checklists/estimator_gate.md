---
component: estimator_gate
title: Estimator and gate
owner: B
spec_sections: ["2.5", "3.4", "17.5"]
tests: ["tests/unit"]
---
# Estimator and gate (`agents/gate`)

## Deterministic (CI gate)
- [x] 100% branch coverage on the eight guardrail rules (`uv run --with pytest-cov pytest tests/unit/test_guardrails.py --cov=agents.gate.guardrails --cov-branch`)
- [x] Property test: margin after discount never below the category floor when the gate passes
- [x] Property test: holdout fraction respected within 1% on 10,000 hashed customers
- [x] `cite_or_drop` rejects a rationale number that is not in `citations`
- [x] Counterfactual arithmetic matches the spreadsheet fixture (`fixtures/estimator/`)
- [x] Runtime invariant: an independent recomputation blocks a play write on mismatch (§17.5) — `agents/gate/invariants.py`, wired into `propose_play`; `tests/unit/test_invariants.py`
- [x] `online_sellby_date` unit tests cover the boundary day and non-food

## Reviewer-verified
- [x] Prior derivation is documented and weak by construction (low pseudo-count, disclosed)
- [x] No LLM output reaches a rupee figure, an arm or a consent decision — rupee figures are recomputed and write-blocked by the §17.5 invariant above; `assign_arm`/`assign` take only `holdout.seed`/`holdout.fraction` (guardrail-validated numeric/string fields), never free text (`tests/unit/test_assignment.py::test_assign_ignores_any_llm_authored_play_fields`); `rule_consent_required` reads only audience fields and the consent store, never the rationale (`tests/unit/test_guardrails.py::test_consent_required_ignores_any_llm_authored_rationale`)
