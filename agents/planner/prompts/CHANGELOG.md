# Planner prompt changelog

- v4 (2026-09-20): step 8 tells the model to delete an uncited number rather than retry citing it
  a third time. Found in the same live re-plan as v3: the model failed `cite_or_drop` on the same
  number five times in a row and exhausted the loop with no play. Root number never conclusively
  identified from the trace (a static replay of the logged rationale/citations does not reproduce
  the failure the live guardrail check reported); `cited_numbers` in agents/gate/guardrails.py was
  separately widened to also treat the tool-computed `guardrails` field as cited, since a
  rationale restating an already-verified guardrail number is not inventing one.
- v3 (2026-09-20): step 2 tells the model to include every reachable segment above an affinity bar
  for deadline-driven objectives, not just the single largest. Found on a live re-plan of the
  chips gap: the model picked one 105-customer segment where the golden play (and the full
  reachable, consented audience) is 315 -- guardrail-legal but left most of the clearance value
  unclaimed, and made the approve beat's chart barely move.
- v2 (2026-09-20): step 4 now spells out the `play_draft` shape and tells the model to repair a draft when a tool returns `error`. Found on the first live Vertex run: Gemini called `estimate_outcome` without `target`, the tool raised, and the whole loop aborted; `estimate_outcome`/`check_guardrails` now return `{"error", "required_shape"}` for an incomplete draft instead of raising.
- v1 (2026-09-12): initial instruction. Tool order fixed; numbers only from tools; policy appended at runtime; play id convention; guardrail anticipation list mirrors agents/gate/guardrails.py.
