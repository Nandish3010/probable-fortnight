# Design notes

Moved from the README: why the loop generalizes, and what Gemini decides versus what code decides.

## Why this generalizes: one decision loop, not a promo bot

The mechanism behind the hook is not specific to food. A `Play` (`docs/schemas/play.schema.json`)
is a single object -- target, mechanic, audience, guardrails, holdout, expected outcome -- and
`agents/gate/guardrails.py` and `agents/gate/estimator.py` never look at what kind of gap produced
it. The gate layer does not look at what kind of gap produced a play. Only the grocery loop ships in
this tree:

1. **Online sell-by is a first-class gap type**, not a side note on expiry: `online_sellby_breach`
   sits alongside `expiry_writeoff`, `stockout_risk`, `rebalance` and `slow_mover` as one of the
   forecast-driven gap types a lot can raise before a deadline.
2. **A guardrailed planner drafts the play.** The ADK Planner Agent (`LlmAgent` in a `LoopAgent`)
   proposes a mechanic; `agents/gate/guardrails.py`'s eight rules gate it before it reaches a
   human, revising the play on a failed guardrail rather than failing outright.
3. **Every play gets a hash holdout.** Assignment (`agents/gate/assignment.py`) splits treated vs
   holdout by a deterministic hash of the customer id on every play, never an all-in send.
4. **Measure updates the estimator's prior.** Every Measure run calls `update_prior()`
   (`agents/gate/estimator.py`, `jobs/measure/run.py`) and writes the new `alpha`/`beta` back to
   `estimator_priors`, keyed by mechanic, category and segment -- the next play of that shape
   starts from what was actually measured, not a static assumption.

The loop closes rather than staying open-ended: the approved play sets a promo flag on its window;
the re-forecast applies the fitted promo lift (a projection; Measure tests it against the holdout)
and the chart moves in the 60-second beat, not a side effect the next Sense run has to catch up to.

## What Gemini decides / what it is never allowed to decide

Each row names the code that owns the decision and the test that fails if that boundary moves.
CI runs `TAAL_MODEL_BACKEND=stub` (scripted models, same tools and code paths), so the left-column
tests prove what the model's output must pass through, not how good the model is.

| Gemini decides | Code | Enforced by |
|---|---|---|
| Reading SKU, best-before date and count from a pallet photo, with a confidence per field | `agents/capture/vision.py:99` (`_vertex_rows`) | `tests/agents/test_vision.py:12`: rows validate against the schema; low-confidence rows are flagged |
| Proposing the play: shape, mechanic (and its parameters), audience segments, rationale; revising after a failed guardrail | `agents/planner/agent.py:101` (`LlmAgent` in a `LoopAgent`, max 3 iterations) | `tests/agents/test_planner.py:50`: the chips coupon fails the margin floor and the revision is a different, passing play |
| Offer copy wording, per segment and language (vertex backend only; Approve attempts `AI.GENERATE_TABLE` under a 3 s budget and falls back to templated copy, the usual outcome on the live demo) | `jobs/sense/copy.py:95` (`AI.GENERATE_TABLE` at `:151`), gated by `validate_copy` at `:168` | `tests/unit/test_copy.py:39`: a variant stating the wrong best-before date is rejected |
| What to say to a customer, and which tool to call | `agents/customer/agent.py:38`, turn loop `agents/chat_runtime.py:160`, envelope clamped at `:180` | `tests/agents/test_customer.py:31` (every scripted conversation in `fixtures/conversations/`); `:88`: the exact on-hand count never reaches the customer |

| Never decided by Gemini | Code | Enforced by |
|---|---|---|
| Every rupee: expected units, margin, cost, counterfactuals | `agents/gate/estimator.py:216` (`estimate`); re-checked when a play is proposed, `agents/planner/tools.py:370` (`check_play_money`) | `tests/unit/test_estimator.py:32` (coupon arithmetic against a hand calculation); `tests/unit/test_invariants.py:45` (a play whose margin was altered after estimation is rejected) |
| Guardrail pass/fail: the eight rules | `agents/gate/guardrails.py:364` asserts the rule table equals `GUARDRAIL_RULES` in `agents/gate/models.py:42-45`; `check` at `:367` | `tests/unit/test_guardrails.py:28` (all eight run, in order); `:155` (consent_required ignores any model-written rationale) |
| Who is in the holdout: arm by hash of (customer, seed); the seed is `seed-<play id>`, set in code when a play is proposed | `agents/planner/tools.py:361` (`propose_play`), `services/api/approve.py:113` calls `agents/gate/assignment.py:23` (`assign_arm`, SHA-256 bucket) | `tests/unit/test_assignment.py:15` (arm is a pure function of seed and id); `:34` (model-written play fields cannot change an arm); `tests/agents/test_holdout_seed.py:24` (a model-written seed is replaced) |
| Consent: whether any offer may reach a customer; what STOP does | `agents/customer/tools.py:54` (`_consent_ok`), checked at `:104`, `:218`, `:260`; `record_stop` at `:354` withdraws consent and drops pending offers | `tests/agents/test_customer_gates.py:15`: after `record_stop`, context, `apply_offer` and `negotiate_offer` all refuse with no model turn |
| Forecast numbers, including the re-forecast on approve | `jobs/sense/forecast.py:127` (statistical model, no LLM); approve re-runs it at `services/api/approve.py:144` | `tests/sql/test_forecast.py:23`: an approved play changes p50 inside its window and nowhere else |
| Discount bounds: the category margin floor on every play; the ad-hoc chat discount ceiling | `agents/gate/guardrails.py:76` (`rule_margin_floor`); `agents/customer/tools.py:274` (`min(ad_hoc_max_discount_pct, margin headroom)`) | `tests/unit/test_guardrails.py:53`; `tests/unit/test_estimator.py:82` (property test: margin never below the floor when the gate passes); `tests/agents/test_customer_gates.py:36` (every catalogue sku) |

Two limits, stated rather than hidden. **STOP recognition is the model's call.** The prompt tells
the Customer Agent to call `record_stop` on "STOP" (`agents/customer/prompts/customer.md:38`), and
only the scripted conversations 10-12 cover that step. What STOP does after the call, and every
consent check after it, is code. **The copy validator checks the percentage and the best-before
date, not rupee amounts** in the text (`jobs/sense/copy.py:168`); a bundle price the model misstates
in words would pass it.
