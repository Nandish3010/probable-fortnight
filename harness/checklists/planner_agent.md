---
component: planner_agent
title: Planner Agent
owner: B
spec_sections: ["5.3", "12"]
tests: ["tests/agents/test_planner.py", "make eval"]
---
# Planner Agent (`agents/planner`)

## Deterministic (CI gate)
- [x] Schema validity >= 95% after revision on the 50 largest eligible gaps (stub backend; `tests/agents/test_planner.py::test_evalset_batch_schema_validity_and_gate_pass` -- a pytest threshold, not `adk eval`)
- [ ] `adk eval` on 50 evalsets recorded from real Gemini runs, `tool_trajectory_avg_score` >= 0.8 (EXACT, args ignored) and `response_match_score` >= 0.8, in stub and vertex mode -- today: 5 stub-derived evalsets, 0/5 pass in stub mode (`eval/raw/adk_eval_2026-09-27/stub_legacy5/scores.json`); the 50-gap selection, recorder, trace-derived evalsets and stub replay are built and rehearsed (synthetic, `eval/raw/adk_eval_2026-09-27/rehearsal_synthetic/`), the real recording and the vertex run are not done
- [x] Gate-pass-after-revision >= 90%
- [x] Trajectory match on the required tool order, stub backend, subsequence check (estimate_outcomes -> propose_play; get_gap/get_candidate_audiences/get_past_plays are fetched by the API and handed to the model as context, not called in the common path)
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
