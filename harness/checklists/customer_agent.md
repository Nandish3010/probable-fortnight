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
- [ ] p95 < 6 s on 50 runs (vertex mode; stub mode records the harness overhead only)
- [ ] Agent Simulation guardrail pass rate >= 95% over ~200 personas (report under `eval/`)
- [x] Every message validates against `docs/schemas/chat_envelope.schema.json`
- [x] `place_order` goes through the in-process FastMCP mock and writes `orders.play_id`

## Reviewer-verified
- [ ] Tone and language per persona
- [x] Wire envelope matches the schema on every message including buttons/list limits
