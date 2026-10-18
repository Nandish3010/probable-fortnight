# Planner prompt changelog

- v8 (2026-10-19, branch planner/markdown-option, not deployed): adds the `markdown` mechanic (site-wide online price
  cut, `markdown_pct`; end date, audience and node-level measurement set by the tools) and one instruction: for large
  lots with little time left, a plain markdown is often best; propose it when it beats targeted plays. Step 2 tells the
  model that `estimate_outcomes` returns the best plain markdown in `alternatives`, and that `propose_play` rejects a
  play recovering more than the tolerance less than it (`beats_markdown`, which outranks a soft policy preference).
  Citation example `est-v1` -> `est-v2`. Reason: the sealed eval of 19 Oct (eval/raw/sealed_2026-10-19/) found the planner
  never chose a markdown and lost 7 of 36 scenarios to the blanket 20% markdown by about INR 55,700 in total.

- v7 (2026-10-12): step 3 now tells the model to state, in the rationale, the recovered-versus-doing-nothing
  figure (`do_nothing_inr` + `play_net_inr`) and the beat over a blanket markdown (`blanket_markdown_inr` +
  `play_net_inr`), each quoted from the estimator result. Reason: eight live Tea runs recorded on 12 Oct
  (`eval/raw/planner_real_traces_tea_2026-10-12b/`) passed cite_or_drop but left the headline figures out of
  the rationale (0 to 6 figures, never the beat). The two sums are not stored fields, so
  `agents/gate/guardrails.py::cited_numbers` now also accepts those two derived figures (and nothing else);
  `tests/unit/test_guardrails.py` pins that an invented near-miss figure is still rejected.

- v6 (2026-09-24): five committed live Vertex traces (`eval/raw/rationale_judge_planner_runs_2026-09-21/`)
  all showed the same schema-validation failures repeating across `propose_play` retries, driving
  elapsed time to 50-62s. Two live re-run passes against the real Vertex backend (not the
  deployed URL) found and fixed, in order:

  Round 1 -- `copy_status` sent as a top-level field instead of nested inside `copy` (the
  prompt's own step-6 rule said "leave `copy_status: pending`" with no nesting shown -- a direct
  instruction/schema mismatch); `audience.filters` sent as `[]` instead of `{}`; a language code
  sent as a locale tag (`en-IN`) instead of the required bare 2-letter code; `citations[]`
  entries sent as a single string (`"policy_version: v1"`) or a `type`/`value` shape instead of
  the required `{type, ref}` object with `type` from a fixed enum.

  Round 2, re-testing `gap_2e7621a152` live after round 1's fix -- `channel` sent as `"app"`
  instead of the enum's `"app_push"`; the play's own required top-level `guardrails` field
  omitted entirely (the model ran `check_guardrails` but never copied its result into the play
  object). Result on that gap: iterations 7 -> 2, elapsed 61.3s -> 36.6s,
  `deterministic_fallback` -> `planner_source: model`.

  Round 3, re-testing all 5 originally-failing gaps live -- 4 of 5 improved (2 fallbacks became
  real model plays; iteration counts dropped on the others), but `gap_f6c4f8c850` got *worse*
  (was `model`/7 iter/50.9s, now `deterministic_fallback`/9 iter/60.9s), surfacing four more real
  contract mismatches: `mechanic` sent as the English word `"markdown"` instead of the enum's
  `"outlet_markdown"`; `mechanic_params` sent as `discount_percentage` instead of `discount_pct`;
  `window` sent as `{"duration_days": N}` instead of explicit `start`/`end` ISO date-times;
  `holdout.seed` sent as `"1"` (fails the schema's 4-character minimum). Also observed: the model
  hit `cite_or_drop` on the same uncited number (`95`) twice in a row and retried the identical
  rationale text a third time anyway, ignoring the prompt's own existing step-6 instruction to
  drop the number instead -- rewrote that instruction with a concrete before/after example
  (delete the whole clause, don't hunt for a citation), but this specific behavior was NOT
  re-verified live after the change (unlike every other fix in this entry, which was); flag it
  as improved, not proven, until re-tested.

  Full before/after evidence for all 5 gaps across all three rounds:
  `eval/raw/planner_prompt_v6_2026-09-24/`. Even after every schema-contract fix, none of the 5
  gaps completed a real model-authored play under 10s -- observed per-iteration latency for a
  single real Gemini round trip on this task ranged 20-43s, so the 10s target is not reachable by
  fixing the contract alone; it needs either fewer round trips per iteration or a fundamentally
  different latency budget, which is a separate, harder problem from what this entry fixes.

  Addendum (2026-10-12, no version bump): every live Tea run (5 of 5) spent attempt 1 on a schema
  rejection for an `id` field in place of the required `play_id`. The prompt now names `play_id`
  explicitly, and `propose_play` accepts a top-level `id` as an alias (agents/planner/tools.py).
  The committed Tea recording (`eval/raw/planner_real_traces_tea_2026-10-12/`) predates this fix.

- v5 (2026-09-21): the Planner now plans a seventh gap type, assortment_gap (the apparel analogue
  of unmet_demand/rebalance, sourced from real stylist asks). `get_candidate_audiences` gained a
  `gap_id` param the model must always pass, so an assortment_gap's real requesting customers
  (stored in the gap's evidence, since the grocery affinity table never covers an apparel sku)
  still reach an audience instead of an empty one.
- v4 (2026-09-20): step 8 tells the model to delete an uncited number rather than retry citing it
  a third time. Found in the same live re-plan as v3: the model failed `cite_or_drop` on the same
  number five times in a row and exhausted the loop with no play. Root number never conclusively
  identified from the trace (a static replay of the logged rationale/citations does not reproduce
  the failure the live guardrail check reported); `cited_numbers` in agents/gate/guardrails.py was
  separately widened to also treat the tool-computed `guardrails` field as cited, since a
  rationale restating an already-verified guardrail number is not inventing one.
- v3 (2026-09-20): step 2 tells the model to include every reachable segment above an affinity bar
  for deadline-driven objectives, not just the single largest. Found on a live re-plan of the
  chips gap: the model picked one 105-customer segment where the golden play (and the full
  reachable, consented audience) is 315 -- guardrail-legal but left most of the clearance value
  unclaimed, and made the approve beat's chart barely move.
- v2 (2026-09-20): step 4 now spells out the `play_draft` shape and tells the model to repair a draft when a tool returns `error`. Found on the first live Vertex run: Gemini called `estimate_outcome` without `target`, the tool raised, and the whole loop aborted; `estimate_outcome`/`check_guardrails` now return `{"error", "required_shape"}` for an incomplete draft instead of raising.
- v1 (2026-09-12): initial instruction. Tool order fixed; numbers only from tools; policy appended at runtime; play id convention; guardrail anticipation list mirrors agents/gate/guardrails.py.
