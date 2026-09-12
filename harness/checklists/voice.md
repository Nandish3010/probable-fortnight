---
component: voice
title: Voice (if kept)
owner: B
spec_sections: ["5.1"]
tests: ["tests/agents/test_voice.py"]
---
# Voice session (`agents/capture`)

Cut first under the §8 drop list; keep vision.

## Deterministic (CI gate)
- [ ] Tool calls fire for the three intents (`get_gaps`, `explain_play`, `approve_play`) on 20 recorded Kannada and English clips
- [ ] Fallback language switch (Kannada -> English) works
- [ ] `approve_play` asks confirmation before the approve call

## Reviewer-verified
- [ ] Spoken play summary matches the play card
