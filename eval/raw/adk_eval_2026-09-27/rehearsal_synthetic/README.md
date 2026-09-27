# Pipeline rehearsal, 27 Sep 2026: synthetic, NOT the planner evaluation

This checks that the pipeline works. It is not a measurement of the planner. No Vertex
credentials were available in the session that produced it (`/root/.gcp/taal-deploy-key.json`
was absent), so the steps that need real Gemini runs did not run. These files show that the
pipeline built for those steps works end to end, and that the trajectory metric can fail.

Steps, all on the stub backend:

1. `python -m harness.record_planner_traces --backend stub --out <scratch>/traces_stub50` recorded
   one run for each of the 50 gaps in `eval/raw/planner_evalset_selection_2026-09-27.json`.
   `stub_traces_summary.json` is its summary, labelled synthetic. The 50 traces themselves are
   not committed, so nobody can mistake them for model traces.
2. `python -m harness.build_fixtures --evalsets-from-traces <scratch>/traces_stub50` built 50
   evalsets plus `test_config.json` (criteria: `tool_trajectory_avg_score` 0.8, EXACT,
   `ignore_args`; `response_match_score` 0.8).
3. Two of those evalsets (`gap_2e7621a152`, `gap_7bcc0cc853`) had their expected tool names and
   `propose_play` verdicts replaced with the shapes of the real Gemini runs committed in
   `eval/raw/planner_prompt_v6_2026-09-24/trace_gap_{2e7621a152,7bcc0cc853}.jsonl`: 7 and 8 tool
   calls, with 2 and 4 rejected `propose_play` calls before the accepted one.
4. `harness/run_evals.py` (stub, the command `make eval` runs; `make eval` itself also gave 50/50) ran against those 50 evalsets twice:
   - `replay_on_scores.json`: with `TAAL_STUB_TRAJECTORY=recorded` (what `harness/run_evals.py`
     sets automatically for recorded-trace evalsets), **50/50 passed**, including both
     real-shaped ones.
   - `replay_off_scores.json`: with `TAAL_STUB_TRAJECTORY=off`, meaning the scripted stub,
     **48/50 passed**. The 2 failures are exactly the two real-shaped evalsets:
     `tool_trajectory_avg_score` 0.0, `response_match_score` 1.0.

What this shows: the recorder, the builder, the replay stub and the criteria fit together, and
the metric catches a trajectory mismatch. Result 4b is the negative control.

What this does not show: anything about Gemini. The 48 stub-vs-stub passes are circular by
construction. The evalsets were restored to the committed 5 afterwards; none of these 50 is
committed.
