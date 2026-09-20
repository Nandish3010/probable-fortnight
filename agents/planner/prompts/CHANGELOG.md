# Planner prompt changelog

- v2 (2026-09-20): step 4 now spells out the `play_draft` shape and tells the model to repair a draft when a tool returns `error`. Found on the first live Vertex run: Gemini called `estimate_outcome` without `target`, the tool raised, and the whole loop aborted; `estimate_outcome`/`check_guardrails` now return `{"error", "required_shape"}` for an incomplete draft instead of raising.
- v1 (2026-09-12): initial instruction. Tool order fixed; numbers only from tools; policy appended at runtime; play id convention; guardrail anticipation list mirrors agents/gate/guardrails.py.
