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
- [ ] p95 < 6 s on 50 runs (vertex mode; stub mode records the harness overhead only) --
  **measured 2026-09-21, does not clear the bar**: 50 real `/chat` calls against a local server on
  the live Vertex backend (`amru-509214`, `asia-south1`, `gemini-2.5-flash`), one fresh
  `X-Taal-Visitor` per call, varied messages (product asks, offers, STOP, browse). 49/50 succeeded;
  p50 5.195s, **p95 7.202s** -- over the 6s bar. One 500 (`jsonschema.exceptions.ValidationError:
  None is not of type 'object'`, model returned `"list": null` instead of omitting the key) is a
  separate, real bug worth fixing but not the cause of the latency miss. Raw per-call data:
  `eval/raw/customer_latency_2026-09-21.json`; summary: `eval/raw/customer_latency_summary_2026-09-21.json`.
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
