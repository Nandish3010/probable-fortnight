---
component: web
title: Web (Play Desk, phone view, chat, judge mode)
owner: C
spec_sections: ["5.6", "10"]
tests: ["make web-test"]
---
# Web (`web/`)

## Deterministic (CI gate, Playwright)
- [x] "Run the 60-second beat" completes in < 30 s with the chart change visible
- [x] "Chat as Meena" first reply < 6 s
- [ ] Reset restores the snapshot for the visitor only
- [ ] Per-visitor sandbox isolation: two sessions do not see each other's approvals
- [x] No console errors on the landing, Play Desk, phone view, chat, Outcomes
- [x] Mobile viewport passes
- [x] LIVE / REPLAY badges present on every panel
- [ ] First paint < 4 s from a cold hit
- [ ] Health strip reads `/health` and turns amber on a failing dependency

## Reviewer-verified
- [ ] Screens match §5.6 (gap card with sell-by countdown and rule, counterfactual bars, guardrails, "Why this play?" drawer, policy editor, Outcomes with "unmeasured")
- [ ] No login wall
