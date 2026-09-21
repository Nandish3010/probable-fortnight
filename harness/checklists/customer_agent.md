---
component: customer_agent
title: Customer Agent
owner: B
spec_sections: ["5.5", "2.6"]
tests: ["tests/agents/test_customer.py", "tests/agents/test_mcp_orders.py"]
---
# Customer Agent (`agents/customer`, `agents/mcp_orders`)

## Deterministic (CI gate)
- [x] 20 scripted conversations under `fixtures/conversations/` pass
- [x] Offer delivered on the first turn with the best-before line
- [x] Out-of-stock -> substitution from live node stock
- [x] Holdout customer asking "any offers?" gets none
- [x] STOP writes `consent.withdrawn_at` and stops delivery
- [x] Coupon stacking refused by `apply_offer`
- [x] p95 < 6 s on 50 runs (vertex mode; stub mode records the harness overhead only) --
  **measured 2026-09-21, clears the bar after a real fix**: the first measurement (same session)
  found p50 5.195s / **p95 7.202s**, over the 6s bar. Root cause: every single-turn `/chat` call
  paid for two sequential live `generateContent` round trips (the model deciding to call
  `get_customer_context`, then a second call to produce the final reply) even on turns that needed
  no other tool -- `get_customer_context` is a pure, deterministic store lookup that gains nothing
  from being a model-invoked tool call. Fixed by prefetching it in Python (`agents/customer/chat.py`,
  the same pattern `agents/stylist/chat.py` already uses for its vision reads) and folding the
  result into the turn text as an already-done tool result, with the prompt told not to call it
  again; a turn needing no other tool now resolves in one round trip instead of two. Re-measured
  with the identical 50-call methodology (same message mix, one fresh `X-Taal-Visitor` per call):
  50/50 succeeded, p50 **4.401s**, p95 **5.752s** -- under the 6s bar. Turns that still need a real
  tool (`list_products`/`get_stock`/etc.) keep two round trips and remain the slower half of the
  distribution; this is a real, if partial, fix, not a full elimination of the underlying
  per-round-trip cost. Before: `eval/raw/customer_latency_2026-09-21.json` /
  `eval/raw/customer_latency_summary_2026-09-21.json`. After:
  `eval/raw/customer_latency_fix_2026-09-21.json` / `eval/raw/customer_latency_fix_summary_2026-09-21.json`.
  See `eval/evaluation.md` for the full write-up.
- [x] Agent Simulation guardrail pass rate >= 95% over ~200 personas (report under `eval/`) -- 190/190
  (100%) live-Vertex personas, `harness/agent_simulation.py`,
  `eval/raw/agent_simulation_2026-09-21.json`, `eval/evaluation.md`. No hosted GCP "Agent
  Simulation" product is reachable for a custom ADK agent in this project (see eval/evaluation.md);
  this harness talks to the real Customer Agent directly instead.
- [x] Every message validates against `docs/schemas/chat_envelope.schema.json`
- [x] `place_order` goes through the in-process FastMCP mock and writes `orders.play_id`
- [x] `get_customer_context` returns a cross-session `memory` of what a customer has recently
  asked for, so a returning customer is proactively told when an item they wanted is back in
  stock instead of starting cold every session
- [x] Every out-of-stock lookup and every off-catalogue ask (including one that matches no
  greeting/browse/sku intent at all) is recorded to `customer_requests` as a demand signal

## Reviewer-verified
- [ ] Tone and language per persona
- [x] Wire envelope matches the schema on every message including buttons/list limits
