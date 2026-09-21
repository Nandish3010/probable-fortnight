---
component: planner_agent
title: Planner Agent
owner: B
spec_sections: ["5.3", "12"]
tests: ["tests/agents/test_planner.py", "make eval"]
---
# Planner Agent (`agents/planner`)

## Deterministic (CI gate)
- [x] `adk eval` on 50 gaps: schema validity >= 95% after revision
- [x] Gate-pass-after-revision >= 90%
- [x] Trajectory match on the required tool order (estimate_outcomes -> propose_play; get_gap/get_candidate_audiences/get_past_plays are fetched by the API and handed to the model as context, not called in the common path)
- [x] The tea gap changes mechanic when the policy fixture changes
- [x] LoopAgent terminates within 3 iterations on 50/50 gaps
- [x] Model ID read from `config/models.toml` only; `thinking_level` from config
- [x] Prompts live in `agents/planner/prompts/*.md` with a changelog

## Reviewer-verified
- [ ] Rationale quality on the 15-item human-labelled subset -- the Gemini-as-judge half is real
  and measured: mean 5.0/5, 15/15 clear the >= 4.0 bar (`harness/rationale_judge.py`,
  `eval/evaluation.md`'s "Gemini-as-judge rationale score, 15-item subset" section,
  `eval/raw/rationale_judge_2026-09-21.json`). Left unticked because the human-labelled agreement
  half genuinely needs an independent person to score the same 15 rationales
  (`eval/raw/rationale_judge_plays_2026-09-21/`) against the written rubric -- not something this
  session can supply itself without it being a self-graded, non-independent label.
- [x] No number in a rationale that is not in `citations`
