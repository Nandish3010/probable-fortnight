---
component: event_log_replay
title: Event log and replay
owner: B
spec_sections: ["10"]
tests: ["tests/api/test_api.py", "tests/agents/test_planner.py"]
---
# Event log and replay (`agents/gate/store.py` events, `services/api` /events)

## Deterministic (CI gate)
- [x] Every ADK event persisted with author, invocation_id, function_call, function_response, text, timestamp, `ts_offset_ms`
- [x] Replay of a golden run renders the same panel states as the live run (snapshot diff) — `web/tests/live/arjun.spec.ts` snapshots the trace panel's rendered text before and after clicking "Replay at 4x" and asserts they are byte-identical
- [x] `GET /events/{run_id}` and the SSE stream emit the same sequence
- [x] Replay timing: original or 4x

## Reviewer-verified
- [x] Trace is readable to a judge (`invocation_id` visible, one line per tool call, revision visible) — `web/tests/live/arjun.spec.ts` asserts more than 3 rendered event lines, an `e-<uuid>` invocation id visible, and the "Guardrail failed: margin_floor... Revising the play." line visible
