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
- [ ] `adk eval` on 50 evalsets recorded from real Gemini runs, `tool_trajectory_avg_score` >= 0.8 (EXACT, args ignored) and `response_match_score` >= 0.8, in stub and vertex mode, needs both stub 50/50 AND vertex >= 45/50 to tick -- today (28 Sep, real 50-gap recording, `eval/raw/planner_traces_2026-09-28/`): stub-with-replay **47/50** (`eval/raw/adk_eval_2026-09-28/stub/scores.json`; the 3 failures are `tool_trajectory_avg_score=1.0` but `response_match_score=0.0` on genuinely empty recorded responses -- ADK's rouge1 scores empty-vs-empty as 0.0 by construction, not a replay defect, see `tests/agents/test_planner.py::test_rouge1_of_empty_vs_empty_is_zero_not_the_replays_fault`); vertex (independent second live run per gap, no deadline) **7/50** both metrics, `tool_trajectory_avg_score` alone 7/50, `response_match_score` alone 42/50 (`eval/raw/adk_eval_2026-09-28/vertex/scores.json`, divergence classes in `eval/raw/adk_eval_2026-09-28/vertex/divergence.json`) -- with one invocation per case and EXACT trajectory matching, this mostly measures run-to-run reproducibility of Gemini's propose_play retry count, not planner correctness; see `eval/evaluation.md` row 5 for the owner decision this raises
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
