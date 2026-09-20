# `no_play` diagnosis -- `gap_chips_ds07`, live Vertex, `run_chips_ds07_v1_bd0a8253`

## What this is

Part A of the `/plan` latency task asks for the full ADK event trace of the failing live run
before touching anything else. That trace (`events/run_chips_ds07_v1_bd0a8253.jsonl`, written by
`agents.planner.run.run_planner_async` -> `LocalStore.append_event`) was never committed -- only
its summary line went into `eval/raw/sweep_vertex_2026-09-20.txt` -- and this session has no
Vertex credentials (no `GOOGLE_APPLICATION_CREDENTIALS`, no ADC; the previous sweep note itself
says it was run "locally" against credentials injected from outside the repo, and `*.a.run.app`
is unreachable from this environment's egress policy). A fresh trace could not be captured here.

This is the diagnosis from what *is* committed: the sweep's summary line and the counting logic
in `agents/planner/run.py`, read carefully rather than guessed.

## The evidence

```
OK  200   110.9s  POST /plan (LIVE Gemini planner)  status=no_play iterations=2 play=None run=run_chips_ds07_v1_bd0a8253
OK  200     0.0s  GET /events/run_chips_ds07_v1_bd0a8253 3 events
```

`run.py`'s event counter appends exactly one event per ADK `Event` yielded by `runner.run_async`,
plus one `cost_governor` event at seq 0 before the loop starts. 3 events total means: 1 governor
event + 2 events from the model. `iterations` increments once per event where
`part.text and ev.author == "planner"` -- i.e. once per turn where the **planner emitted plain
text** (as opposed to a function call). `iterations == 2` with only 2 non-governor events means
**both** of those events were text, and **neither** was a function call: across the whole
110.9-second, two-iteration run, `check_guardrails`, `estimate_outcome` and `propose_play` were
never called, and (this being before Part B's context-injection change) neither were `get_gap` or
`get_candidate_audiences`. A successful stub run on the same gap produces 23 events and calls
`propose_play` exactly once with `valid: true`; this run called nothing.

That rules out the guardrail- and schema-rejection hypotheses directly: `check_guardrails` and
`propose_play` responses are what would show a rejected rule or a validation error, and neither
tool was ever invoked. It also rules out a swallowed API error -- `run_planner_async` does not
catch exceptions from `runner.run_async`; an API error would have raised out of the whole call,
not produced two clean text events and a `no_play` return. What's left, and what the event shape
actually shows, is **protocol drift**: the model produced two turns of prose (most likely
attempting to reason through the play in text, or asking a clarifying question, or restating the
procedure back) instead of ever emitting a `function_call` part for `get_gap`, the first
mandatory step the (pre-Part-B) prompt asked for.

## Why, not just what

Two things converge to make this the expected failure mode rather than a fluke, both already
fixable by Part B and both fixed in this change:

1. **`agents/planner/agent.py` line 56 (pre-fix) read only `thinking.planner_final` ("medium",
   `thinking_budget=1024`) and applied it to every turn**, including the very first turn where the
   model has seen nothing but a nine-step procedural instruction and is meant to emit a single
   `get_gap` call. `thinking.planner_route` ("low", budget 0) existed in `config/models.toml` and
   was never read by anything. A non-zero thinking budget on the very first turn, on top of a long
   strict-ordering instruction plus a JSON output contract, is exactly the combination the task
   description names as "a known recipe for a model narrating a plan in prose instead of emitting
   function calls" -- and commit `ccc5107`'s addition of a `cite_or_drop`-retry cap to the same
   prompt is independent evidence that prose drift under this instruction had already been
   observed once, for a different step.
2. **Eleven sequential round trips over a growing context is itself pressure toward drift.** Each
   round trip re-sends the full accumulated transcript; a model asked to hold a strict call order
   in mind over that many turns, with thinking enabled on all of them, has more opportunity to
   lose the thread than one asked to make two or three well-scoped decisions.

## What this change does about it (Part B, this commit)

- `agents/planner/agent.py`: `planner_route` (budget 0) now drives every turn except the one
  where the model has already seen `estimate_outcomes`' results (i.e. is choosing a candidate and
  writing the rationale), which gets `planner_final`. Wired via a `before_model_callback` that
  inspects the transcript for an `estimate_outcomes` function response, since ADK sets
  `generate_content_config` once per agent, not once per call.
- `get_gap`, `get_candidate_audiences` and `get_past_plays` are no longer steps the model must
  remember to call in order: `run.py` fetches them itself (deterministic reads) and hands the
  results to the model as context. There is no longer a first step whose omission looks like
  silent success to a model under thinking pressure.
- `estimate_outcome` -> `estimate_outcomes` (batched: one call for every candidate draft) and the
  explicit `check_guardrails` step is gone from the required procedure (`propose_play` already ran
  the same check internally; the model can now revise straight from its rejection). The instruction
  in `prompts/planner.md` is shorter and names two tool calls, not five.
- Part D (same commit): `run_planner_async` now enforces a wall-clock deadline
  (`TAAL_PLANNER_DEADLINE_S`, default 8s) around the live model loop, and falls back to
  `agents/planner/deterministic.py` -- the same drafting/estimator/guardrail pipeline the stub
  model already drives, run directly with no LLM -- on either a timeout or a `no_play` result. The
  fallback is labelled `planner_source: "deterministic_fallback"` in the result and is never
  merged into the "live model" label a judge would see.

## What is not verified here

None of the above has been confirmed against a live Vertex call from this session, for the
credentials reason stated at the top. The stub-backend behaviour (same drafting/estimator/
guardrail pipeline, now reached through fewer tool calls) is verified by `make verify`; the
round-trip count for a live call is a design change, not yet a measured one. Re-running
`agents.planner.run.run_planner` with `TAAL_MODEL_BACKEND=vertex` and real credentials, and
diffing the resulting `events/<run_id>.jsonl` against this note's predictions, is the next step
and is not something this session could do.
