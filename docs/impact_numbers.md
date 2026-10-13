# Impact in numbers (seeded tenant)

Moved from the README. Figures measured on 2026-09-24, before the apparel path was removed from the tree.

Every number below is reproduced from a committed evidence file or a named code constant, not
typed by hand; see `eval/raw/docs_truth_sweep_2026-09-27/impact_numbers.py` for the script that
reproduced each one. The figures were measured on 2026-09-24, before the apparel path was removed
from the tree; they include 5 `assortment_gap` rows (₹16,443 of the exposure) that the current
generator no longer produces.

| What | Number | Label | Source |
|---|---|---|---|
| 28-day exposure on the seeded tenant (one Sense run, 555 gaps, of which 5 are `assortment_gap` rows the current generator no longer makes, so 550 grocery gaps; the 28-day horizon bounds 4 of the six gap types Sense produces today, `agents/gate/models.py:34-36` -- the other 2 (`stockout_risk`, `unmet_demand`) use each node's `lead_time_days` instead; the enum keeps a seventh name, `assortment_gap`, for schema compatibility only, 3-5 days in the seeded tenant, `data/generator/generate.py:119`) | ₹1,795,464 | seeded | `eval/raw/portfolio_2026-09-24.json` (`totals/exposure_inr`); horizon = `HORIZON`, `jobs/sense/forecast.py:31`; reproduced in `impact_numbers.json` |
| Plays planned | 424 | seeded | `eval/raw/portfolio_2026-09-24.json` (`planned/count`); reproduced in `impact_numbers.json` |
| Expected margin at the default response prior (5%, `agents/gate/estimator.py:35-36`) -- sales margin ₹206,205 plus write-off avoided (net of transfer cost) ₹141,151 | ₹347,356 total | projected | `eval/raw/portfolio_2026-09-24.json` (`plays[*].expected_outcome.margin_inr`, split by mechanic); transfer-cost formula per the `agents/gate/estimator.py` docstring; reproduced in `impact_numbers.json` |
| Monthly running cost of this deployment -- usage measured over the trailing 30 days to 2026-09-23 on `gemini-2.5-flash` (not re-measured on `gemini-3.5-flash`), priced at Google's public list rates; not a bill | ₹486 | measured (usage), list-priced; not a bill | `eval/raw/cost_measurement_2026-09-23.json` (`modeled/total_inr`; method "modeled_from_measured_usage": usage quantities measured over the trailing 30 days, priced at Google's public list rates) |
| Forecast backtest, synthetic tenant -- mean MAPE over 63 tier-origin rows (9 category tiers x 7 rolling origins, 7-day horizon) and pooled WAPE over the same scored series-days | MAPE 0.133 (tiers 0.107 to 0.221); WAPE 0.113 | seeded | `eval/raw/backtest_rows_2026-09-20.jsonl` (MAPE); `synthetic_reference` in `eval/raw/external_backtest_2026-10-09.json` (both); `uv run python -m jobs.sense.backtest` |
| **Real data** -- same backtest and forecaster on UCI Online Retail II (top 300 SKUs, 8 rolling origins); gap detector: 0 gaps, none computable (no stock or expiry in the data) | MAPE 3.79 (median per-day error 0.78); WAPE 0.83; 0 gaps | measured on public data | `eval/raw/external_backtest_2026-10-09.json`; method and caveats in [`eval/external_backtest.md`](../eval/external_backtest.md). Caveat: a UK gift wholesaler, not grocery, with lumpy daily sales; the figure says the method is weak on lumpy daily demand, not what grocery will do |
| Hero play (Tea, `gap_tea_ds04`), recovered versus doing nothing, and beat over a blanket 20% markdown -- recorded Gemini run `c/run_02`, 12 Oct 2026 | ₹9,191 / ₹6,186 | projected, seeded tenant | ₹9,191 is the estimator's figure (`expected_outcome.margin_inr` 9,191.29 = waste avoided ₹9,397 minus transfer cost ₹206). ₹6,186 is derived, not a stored estimator field: `counterfactuals.blanket_markdown_inr` 32,015.18 plus `play_net_inr` -25,828.71 = 6,186.47, a sum `cite_or_drop` accepts in the final proposal's rationale (`agents/gate/guardrails.py`); `eval/raw/tea_recorded_beat_2026-10-12.json`; detail in [`hero_plays.md`](hero_plays.md) |
| Who pays -- a category or supply-chain head; price anchor is a share of waste avoided | -- | projected | `docs/DECISIONS.md` section 18.7 |

India scale, as reported (the letter itself was not opened): Inc42 (22 Jul 2026), citing Eternal's Q1 FY27 shareholder letter, reports Blinkit's inventory losses (expiry, shrinkage, damage, pilferage, transit) at about 1.8% of net order value. With the same article's Q1 NOV of ₹17,132 crore and 2,443 stores, that is ₹17,132 crore / 2,443 = ₹7.01 crore per store per quarter, x 4 = ₹28.05 crore a year, x 1.8% = about ₹0.5 crore (₹50 lakh) of inventory loss per store per year. This is all inventory loss, not only the near-expiry stock Taal targets, and it annualises one quarter; it is context for scale, not a Taal result.

Buyer and pricing basis: the buyer is the category / supply-chain head, who owns write-off; the basis is either a fee per dark store per month or a percentage of rupees rescued measured against the holdout (`fee = pct x rupees rescued vs holdout`). No price point is set until a pilot measures that lift.

Projected margin less run cost, illustration, synthetic and projected, not a quote: projected margin per node less run cost per node = ₹347,356 / 16 nodes - ₹486 / 16 nodes, about ₹21,710 - ₹30. This is not a break-even: no fee is set.
