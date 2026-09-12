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
- [x] Reset restores the snapshot for the visitor only — `web/tests/live/judge.spec.ts`: after visitor A resets, their own play returns to `proposed`
- [x] Per-visitor sandbox isolation: two sessions do not see each other's approvals — same test: a second, fresh visitor still sees the play as `proposed` after the first visitor approved it
- [x] No console errors on the landing, Play Desk, phone view, chat, Outcomes
- [x] Mobile viewport passes
- [x] LIVE / REPLAY badges present on every panel
- [x] First paint < 4 s from a cold hit — `web/tests/live/judge.spec.ts::first paint under 4s from a cold hit`, measured via the browser's own `first-contentful-paint` Paint Timing entry
- [x] Health strip reads `/health` and turns amber on a failing dependency — `web/tests/live/judge.spec.ts::health strip turns amber when a dependency check fails`, intercepts a real `/health` response and flips one check to `ok: false`

## Reviewer-verified
- [x] Screens match §5.6 (gap card with sell-by countdown and rule, counterfactual bars, guardrails, "Why this play?" drawer, policy editor, Outcomes with "unmeasured") — present in `GapCard.tsx`, `CounterfactualBars.tsx`, `GuardrailList.tsx`, the Play Desk's "Why this play?" drawer and `PolicyEditor.tsx`, and the Outcomes table's unmeasured pill
- [x] No login wall — no auth page, middleware, or protected route anywhere in `web/app`; every route (including judge mode) opens directly
