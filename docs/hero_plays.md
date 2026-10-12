# The two recorded Gemini plays

Moved from the README.

## Tea (hero)

The 60-second beat opens on `gap_tea_ds04`: 103 units of Darjeeling Tea 100G at dark store DS-04,
₹35,020 at stake, online sell-by 6 October 2026. Its Desk trace is a real, committed Gemini
recording, badged `Recorded from Gemini · 12 Oct 2026`: 16 independent live Vertex runs in two sets
(`gemini-3.5-flash`). Set b, 8 runs on the then-current prompt v6, all reached `proposed` with 0 fallbacks in
19.1 to 28.9 s, and 7 of 8 passed on the first attempt. Set c, 8 runs on prompt v7, all reached `proposed` with
0 fallbacks in 19.0 to 31.4 s, 7 of 8 with no rejection, and every run states both figures (the improvement over
doing nothing and the beat over a blanket markdown). `harness/seed_plays.py` seeds the pinned run, `c/run_02`,
which was accepted on its first attempt (pin in `eval/raw/seed_pins.json`). The play
is a transfer of the 103 units to OUT-01 plus a nudge to 394 consented customers (468 before
consent) across 5 segments, expected margin ₹9,191 (waste avoided ₹9,397 minus transfer cost
₹206), and it passed all eight guardrails. It beats a blanket 20% markdown by ₹6,186
(`counterfactuals.play_net_inr` on the play; `GET /plays`; snapshot in
`eval/raw/tea_recorded_beat_2026-10-12.json`, recorded runs in
`eval/raw/planner_real_traces_tea_2026-10-12/`). Approval assigns 355 treated and 39
holdout customers by hash, writes the play into `future_regressors`, and moves the projected
write-off from ₹35,186 to ₹28,659 (local approve on the seeded tenant, 12 Oct 2026; the deployed
service shows the same after the next deploy).

## Chips

The second Gemini-recorded demo gap is `gap_chips_ds07`: 368 units of Masala Chips at dark store
DS-07, ₹9,200 at stake, online sell-by in 6 days. Its Desk trace is a real, committed Gemini
recording, badged `Recorded from Gemini · 10 Oct 2026`: five independent live Vertex runs
(`harness/record_flagship_traces.py --gap gap_chips_ds07 --runs 5`, `TAAL_MODEL_BACKEND=vertex`,
`gemini-3.5-flash`, prompt v6) all reached `proposed` with 0 fallbacks in 21.8 to 27.6 s;
`harness/seed_plays.py` picked run 5 to seed the play. Run 5 needed a second `propose_play`
attempt (the first was rejected on a schema error, an unexpected `id` field), then passed all eight
guardrails: a bundle of Masala Chips 200G with Cola Classic 250ML, ₹50 for the pair, offered to 352
consented customers (426 before consent) across 6 segments through the web-chat channel. The model
considered and rejected a Coconut Water bundle at ₹55, an Orange Juice bundle at ₹50 and a transfer
to OUT-03 (negative expected margin, -₹127.12); `margin_floor` passed at 10.44% net margin against
the snacks category's 8% floor. The planner loop is capped at 3 revisions; the run used 1. Approval
assigns 323 treated and 29 holdout customers by hash, and Meena's chat then delivers the offer.
This chips play does not beat the baseline: its net is -₹8,468 against -₹8,189 for a blanket 20%
markdown, about ₹279 worse, and the Desk shows both. The figures are in
`eval/raw/planner_real_traces_2026-10-10/summary.json` and
`eval/raw/planner_real_traces_2026-10-10/run_05/{play,result}.json`. On the deployed service,
**Change policy → re-plan** instead runs Gemini live on demand: the Desk streams each tool call and
guardrail check as it happens, and if no valid play arrives within the 90 s deadline set for the
deployed service, the deterministic-rules fallback runs instead, badged "Rules (fallback)" with the
reason shown. Three live re-plans on the deployed service on 10 Oct (Tea, then Chips twice) all returned
a model-planned play with no fallback, in 27.5 to 30.3 s server-side
(`eval/raw/live_replan_timing_2026-10-10.json`); the same test on 9 Oct, before the fix, fell back to
rules in 2 of 3 runs (`eval/raw/live_replan_timing_2026-10-09.json`).
