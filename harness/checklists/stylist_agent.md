---
component: stylist_agent
title: Stylist Agent
owner: B
spec_sections: ["5.9"]
tests: ["tests/agents/test_stylist.py", "tests/agents/test_stylist_vision.py", "tests/unit/test_colour.py", "tests/unit/test_apparel_generator.py", "tests/sql/test_style_trends.py"]
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
- [x] Checkout is not offered; asking to order gets a clear "not available in this build" reply
- [x] STOP ends the conversation with no consent side effect (the stylist never markets)
- [x] `forget my skin tone` withdraws the `style_profile` consent row and deletes the saved profile
- [x] `style_requests` and `style_trends` never carry a skin-tone field
- [x] `jobs/sense/trends.py` aggregates `style_requests` into `style_trends`, kept only at or above
  `style_trends_min_asks` within `style_trends_lookback_days`

## Reviewer-verified
- [ ] Tone and language per persona
- [ ] Pairing reasons and skin-tone notes read as styling advice, not as unexplained scores
