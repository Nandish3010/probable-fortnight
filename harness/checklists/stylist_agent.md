---
component: stylist_agent
title: Stylist Agent
owner: B
spec_sections: ["5.9"]
tests: ["tests/agents/test_stylist.py", "tests/agents/test_stylist_vision.py", "tests/unit/test_colour.py", "tests/unit/test_apparel_generator.py", "tests/sql/test_style_trends.py", "tests/sql/test_gaps.py", "tests/contract/test_tool_schemas.py", "tests/sql/test_measure_tables.py"]
---
# Stylist Agent (`agents/stylist`)

## Deterministic (CI gate)
- [x] 14 scripted conversations under `fixtures/conversations_stylist/` pass
- [x] Colour theory (the 12-hue wheel, pairing scores, skin-tone rules) is plain Python in
  `agents/stylist/colour.py`; no LLM scores a pairing or resolves a colour family
- [x] Every ask -- a hit or a miss, from `find_apparel` or `suggest_pairings` -- is recorded to
  `style_requests` deterministically, never as an LLM decision
- [x] An unknown colour degrades to neutral-only suggestions instead of failing
- [x] A garment or selfie photo read validates its schema; a low-confidence read is said out loud
  before anything is suggested, and a selfie read is never saved without the customer confirming it
- [x] The stylist and grocery agents never share ADK sessions for the same `customer_id:web`
- [x] Every message validates against `docs/schemas/chat_envelope.schema.json`
- [x] Checkout goes through the same MCP order mock the grocery Customer Agent uses
  (`apply_offer`/`place_order`); redeeming twice is refused ("already redeemed")
- [x] `jobs/sense/gaps.py` resolves real, unfulfilled `style_requests` into an `assortment_gap`
  the same shape as `rebalance` (surplus at another node in-cluster), never when no catalogue sku
  matches or no in-cluster node carries it
- [x] `get_candidate_audiences` reaches an assortment_gap's real askers via
  `evidence.requesting_customer_ids`, since the grocery affinity table never covers an apparel sku
- [x] `jobs/measure/run.py` resolves an apparel sku via `agents/gate/store.py::load_catalogue`
  (merged with grocery `products`) and does not let one play's degenerate (zero-holdout) small
  audience crash measurement for every other play in the tenant
- [x] STOP ends the conversation with no consent side effect (the stylist never markets)
- [x] `forget my skin tone` withdraws the `style_profile` consent row and deletes the saved profile
- [x] `style_requests` and `style_trends` never carry a skin-tone field
- [x] `jobs/sense/trends.py` aggregates `style_requests` into `style_trends`, kept only at or above
  `style_trends_min_asks` within `style_trends_lookback_days`

## Reviewer-verified
- [ ] Tone and language per persona
- [ ] Pairing reasons and skin-tone notes read as styling advice, not as unexplained scores
