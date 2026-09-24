# Impact math: `play_chips_ds07_v1`, worked from committed data

This is the arithmetic behind the counterfactual card, the Outcomes screen, the deck and the
video narration. Every number below is either read directly from
`fixtures/plays/valid/play_chips_ds07_v1.json` (the committed play) or derived from
`agents/gate/estimator.py`'s own formulas (see its module docstring) applied to that play's
inputs. Nothing here is estimated by eye.

## Inputs (all cited)

| Quantity | Value | Source |
|---|---|---|
| `units_at_risk` | 368 | `play_chips_ds07_v1.json` → `target.units` |
| `unit_cost` | ₹25.00 | `counterfactuals.do_nothing_inr` (9200.00) ÷ `units_at_risk` (368) |
| `list_price` | ₹30.00 | back-solved from the rejected coupon alternative: net price 25.50 at a 15% discount → `25.50 / 0.85` |
| `baseline_forecast_units` | 72.23 | `EstimatorContext.baseline_forecast_units` for this gap, read live from `.local/data/gaps.jsonl` → `evidence.projected_sellthrough` (regenerate with `make generate` to reproduce; see "Reproducing this" below) |
| `markdown_elasticity` | 4.0 | `config/tenant.demo.toml` thresholds, read the same way |
| `blanket_markdown_pct` | 20% | `counterfactuals.blanket_markdown_pct` |
| play `units` (expected) | 21.67 | `expected_outcome.units` |
| play `margin_inr` (expected) | ₹235.14 | `expected_outcome.margin_inr` |
| play `discount_cost_inr` (expected) | ₹86.69 | `expected_outcome.discount_cost_inr` |
| play `waste_avoided_inr` (expected) | ₹541.80 | `expected_outcome.waste_avoided_inr` |
| `do_nothing_inr` | ₹9,200.00 | `counterfactuals.do_nothing_inr` |
| `blanket_markdown_inr` | ₹8,188.78 | `counterfactuals.blanket_markdown_inr` |

## Part 1.1 — Same axis: cost of write-off, for all three options

`do_nothing_inr` and `blanket_markdown_inr` are already costs by the estimator's own definition
(`agents/gate/estimator.py::counterfactuals`). The play has no equivalent figure committed on the
play object — `expected_outcome.discount_cost_inr` alone (₹86.69) is **not** comparable, because
it only prices the 21.67 units the play expects to sell and says nothing about the 346.33 units
of the same 368-unit lot the play does not touch. This is the defect: the existing
`CounterfactualBars.tsx` plots `discount_cost_inr` next to `do_nothing_inr` and
`blanket_markdown_inr`, i.e. one uncovered lot's true write-off cost against one covered lot's
sliver of discount cost. That comparison is why the play's bar has looked artificially small.

The play's comparable figure, built from the same two pieces `blanket_markdown_inr` uses
(discount given on units sold + write-off cost on units not sold):

```
residual_writeoff_play = (units_at_risk - units) * unit_cost
                        = (368 - 21.67) * 25.00
                        = 346.33 * 25.00
                        = 8,658.25

play_writeoff_axis = discount_cost_inr + residual_writeoff_play
                    = 86.69 + 8,658.25
                    = 8,744.94
```

| Option | Write-off-axis cost (₹, lower is better) |
|---|---|
| Do nothing | 9,200.00 |
| Blanket markdown (20%) | 8,188.78 |
| This play | 8,744.94 |

**Blanket markdown is cheaper than the play on this axis.** See Part 1.3.

## Part 1.2 — Same axis: net margin retained, for all three options

Net margin retained = actual profit earned on units sold, minus the cost of inventory in the
same 368-unit lot that ends up written off. This charges every option for the same residual it
does not clear, and credits the play's own mechanic margin (not merely a discount figure).

```
do_nothing:
  margin earned  = 0                      (nothing sold)
  write-off cost = units_at_risk * unit_cost = 368 * 25.00 = 9,200.00
  net margin retained = 0 - 9,200.00 = -9,200.00

blanket markdown (20%):
  discount_given (margin given away on the 72.23 baseline units that were going to sell at
    full price with no intervention at all) = baseline_forecast_units * 0.20 * list_price
                                             = 72.23 * 0.20 * 30.00 = 433.38
  uplift_units (extra at-risk units the price cut is modelled to move)
                                             = baseline_forecast_units * 0.20 * markdown_elasticity
                                             = 72.23 * 0.20 * 4.0 = 57.78
  remaining_writeoff = max(0, units_at_risk - uplift_units) * unit_cost
                      = max(0, 368 - 57.78) * 25.00 = 310.22 * 25.00 = 7,755.40
  net margin retained = -(discount_given + remaining_writeoff) = -(433.38 + 7,755.40) = -8,188.78
  (this is exactly counterfactuals.blanket_markdown_inr, negated -- the estimator's own
  blanket-markdown figure already is a net-margin-destroyed number, it is just currently
  charted as a bare "cost" alongside numbers that are not costed the same way)

this play:
  residual_writeoff_play = (368 - 21.67) * 25.00 = 8,658.25    (as in Part 1.1)
  net margin retained = margin_inr - residual_writeoff_play
                       = 235.14 - 8,658.25 = -8,423.11
```

| Option | Net margin retained (₹, higher is better) |
|---|---|
| Do nothing | -9,200.00 |
| Blanket markdown (20%) | -8,188.78 |
| This play | -8,423.11 |

**Reported honestly: on this single lot, blanket markdown still edges out the play by ₹234.33 in
raw net margin retained** (-8,188.78 vs -8,423.11), because the play's bundle only clears 21.67 of
368 units and the remaining 346.33 are still charged as a full write-off. Both clearly beat doing
nothing. This repo does not inflate that result to make the play look like the bigger number —
see "What actually is favourable" below.

## Part 1.3 — Confirm/refute: does blanket markdown beat the targeted play on write-off cost alone?

**Confirmed.** 8,188.78 < 8,744.94 (Part 1.1). A write-off-axis chart is therefore actively
misleading in the play's favour only if it uses the play's uncorrected `discount_cost_inr`
(₹86.69) instead of the comparable `play_writeoff_axis` figure (₹8,744.94) computed above; done
correctly, the write-off axis in fact favours blanket markdown over the play, not the other way
around. **A write-off-axis chart must not ship** — not because it makes the play look bad
(corrected, it still does, honestly), but because the version that would ship without this
correction (comparing `discount_cost_inr` to `do_nothing_inr`) actively misrepresents both bars.

## What actually is favourable, honestly

Neither axis makes the play's *total* number for this one lot beat blanket markdown's. What is
true, and defensible, and visible on the net-margin-retained axis once it is decomposed:

- **Blanket markdown's number is only competitive because it destroys margin on volume that
  never needed help.** ₹433.38 of its ₹8,188.78 write-off-equivalent is margin given away on the
  72.23 units that were projected to sell at full price with no intervention at all
  (`baseline_forecast_units`). The play never touches that volume — its ₹86.69 discount cost is
  spent only on the 315 consented customers targeted at the batch actually at risk.
- **The play is capital-efficient where blanket markdown is not**: ₹235.14 of real margin for
  ₹86.69 spent (2.7x) on the play, against a mechanic (blanket markdown) that the estimator
  credits with generating no positive margin anywhere -- only a smaller loss than doing nothing.
- **This is one lot.** The play was never pitched as clearing all 368 units by itself; the
  rationale's own citation, "prefer bundles and transfers over blanket markdowns; markdowns are
  the last lever," describes a sequencing policy, not a claim that one small play replaces a
  blanket markdown on the same inventory. The number that actually makes the business case is the
  nightly portfolio across every planner-eligible gap (Part 3 / `eval/raw/portfolio_*.json`),
  which is real scale this repo already computes, not a one-lot argument stretched further than
  it honestly goes.

The counterfactual card (Part 2) therefore ships the net-margin-retained axis with blanket
markdown's baseline giveaway broken out as its own visible segment, labelled a projection, with
the play's positive margin visible too -- an honest chart where doing nothing is clearly worst,
blanket markdown's destructiveness on volume that never needed help is visible, and the play's
efficiency is visible, without claiming the play's single-lot total beats blanket markdown's.

## Reproducing this

```
make generate   # seeded tenant -> Sense -> demo plays into .local/data (as-of 2026-09-12)
uv run python -c "
from agents.planner.context import PlannerContext, set_context
from agents.planner.tools import _estimator_context
import json
ctx = PlannerContext.build('.local/data', run_id='inspect'); set_context(ctx)
play = json.loads([r for r in (json.loads(l) for l in open('.local/data/plays.jsonl')) if r['play_id']=='play_chips_ds07_v1'][-1]['play_json'])
ectx = _estimator_context(ctx, play)
print(ectx.product.unit_cost, ectx.product.list_price, ectx.baseline_forecast_units, ectx.markdown_elasticity)
"
```

All figures above were reproduced this way against the seeded tenant (seed `20260912`,
as-of `2026-09-12`), which is deterministic and matches the committed
`fixtures/plays/valid/play_chips_ds07_v1.json` exactly.

## Part 3 — The portfolio, not one lot

`play_chips_ds07_v1` is one worked example on one 368-unit lot. The number that actually makes
the business case is every planner-eligible gap from the same Sense run, planned by the same
deterministic drafter and estimator (`agents/planner/deterministic.py`) with no model calls, run
with `python -m jobs.portfolio --out eval/raw/portfolio_<date>.json`
(`jobs/portfolio/run.py`). Full per-gap output is committed at `eval/raw/portfolio_2026-09-24.json`
(424 plays); the totals below are that file's own summary block.

| | |
|---|---|
| Gaps in the run (`sense_20260912_baseline_2aaad73c`) | 555 |
| Total exposure | ₹1,795,463.92 |
| ...of which online sell-by breaches | 330 gaps, ₹1,499,536.95 |
| Planner-eligible (>= ₹500 at stake) | 428 |
| Triaged out by the Cost Governor | 127 gaps, ₹28,170.54 of exposure -- each below the ₹500 threshold, templated suggestion only, no estimator or model cost spent |
| Planned (valid play drafted) | 424 |
| Eligible but no valid play (every candidate failed a guardrail) | 4 gaps, ₹15,984.64 |
| Portfolio-wide do-nothing (write-off) | ₹1,837,170.32 |
| Portfolio-wide blanket markdown (20%, per gap) | ₹1,369,538.96 |
| Expected units moved across all 424 planned plays | 9,142.64 |
| Expected margin across all 424 planned plays | ₹347,355.96 |
| Expected waste avoided across all 424 planned plays | ₹706,183.28 |

`do_nothing_inr` here (₹1,837,170.32) is not identical to total exposure (₹1,795,463.92) because
a few gap types (`unmet_demand`, `assortment_gap`) price `rupees_at_stake` off lost margin rather
than unit cost, while the estimator's `do_nothing_inr` is always `units_at_risk * unit_cost`
(`agents/gate/estimator.py::counterfactuals`) -- both are cited, neither is rounded to match the
other.

This is the number worth putting in front of a category head: not "one bundle saved ₹235," but
"424 targeted plays, drafted overnight with no model calls, project ₹347,355.96 of margin and
₹706,183.28 of waste avoided against a ₹1.8M exposure this week alone" -- and it needs no pilot to
say, because it is arithmetic over data already generated, not a forecast of a forecast.
