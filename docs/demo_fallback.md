# Live-demo fallback

For a live presentation of Taal. If Gemini is slow or returns an error on stage, switch to a pre-opened second tab and say which one you are showing.

## Before you present

1. Open the live app in tab 1 and run the judge path once (Run the 60-second beat, Approve, Chat as Ravi) so both Cloud Run services are warm.
2. In tab 2, open the demo video at the Plan and Approve scenes (link in the README).
3. In tab 3, keep the recorded Tea run: `eval/raw/tea_recorded_beat_2026-10-12.json` (the committed Gemini run behind the Desk), and `eval/raw/plan_live_2026-10-12.md` (22 of 24 live plans, 11 Oct).

## What the app itself does when a model call fails

| Situation | What the audience sees |
|---|---|
| Primary model answers 404, 429 or 5xx | The call is retried on `gemini-3.5-flash-lite` (global endpoint), `config/models.toml` |
| Both models unavailable (chat) | The API returns HTTP 503 `model_unavailable` with `Retry-After`; retry after that many seconds |
| Plan live misses its deadline | A deterministic rules plan is used and the API marks it `deterministic_rules`, not Gemini |
| Fair-use limit reached | HTTP 429 with `Retry-After`; wait and retry |
| Cold start after idle | First load takes about 10 s |

The Desk, Approve and Outcomes do not need a live model call: the Tea play is a recorded Gemini run and the offer copy is stored. Only Plan live, chat and real photo uploads call Gemini live.

## What to say

"This is a live call to Gemini; it is slow right now, so here is the same step recorded on 12 Oct." Then show tab 2 or 3, and retry tab 1 afterwards.
