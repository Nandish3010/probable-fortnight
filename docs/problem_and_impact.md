# The hook and the impact table

Moved from the README on 14 Oct 2026, text unchanged except link paths. The README carries the current short version; dated figures below are as of the date they name.

## The hook

FSSAI, India's food regulator, sent e-commerce food business operators an advisory on 3 December 2024 ([file no. RCD-13/1/2024-Regulatory-FSSAI(E-13150)](https://fssai.gov.in/upload/advisories/2024/12/674efa161d756Adobe%20Scan%203%20Dec%202024.pdf), paragraph 4): "FSSAI mandates that products must have a minimum shelf life of 30% or at least 45 days before expiry, at the time of delivery." It is an advisory, not a gazetted rule, and it leaves open 30% of what. **The reading below is Taal's configurable default, not FSSAI text.** Taal applies it as a tenant-set, versioned rule (`config/tenant.demo.toml`, `sellby_rule`): a 90-day-shelf-life pack of chips that expires in **33 days** needs 27 days left (30% of 90) and can be sold online for **6** more days. Forecasting tools treat expiry as the deadline; Taal makes the online sell-by cut-off a first-class gap type, shown on every gap card.

## Impact in numbers

Measured 24 Sep 2026 on the seeded tenant; every number comes from a committed evidence file (full table: [`docs/impact_numbers.md`](impact_numbers.md)).

| What | Number | Label | Source |
|---|---|---|---|
| 28-day exposure, one Sense run (555 gaps, incl. 5 assortment rows the generator no longer makes) | ₹1,795,464 | seeded | `eval/raw/portfolio_2026-09-24.json` |
| Plays planned | 424 | seeded | same file |
| Expected margin per 28-day run at the default 5% response prior (sales margin ₹206,205 plus write-off avoided ₹141,151) | ₹347,356 | projected | same file; `docs/impact_math.md` |
| The same estimate at a 2% / 10% response prior instead of 5% (550 grocery gaps; 421 / 423 plays) | ₹140,728 / ₹619,165 | projected | `eval/raw/portfolio_prior_sensitivity_2026-10-09.json` |
| Monthly run cost, usage to 23 Sep 2026 on gemini-2.5-flash, no plays in the window, list-priced | ₹486 | measured usage; not a bill | `eval/raw/cost_measurement_2026-09-23.json` |
| Forecast backtest: synthetic tenant / public non-grocery data | WAPE 0.113 / 0.83 | seeded / public | `eval/raw/external_backtest_2026-10-09.json`; [`eval/external_backtest.md`](../eval/external_backtest.md) |

India scale (Inc42 on Blinkit's inventory losses), buyer and pricing basis, and the projected margin less run cost per node: [`docs/impact_numbers.md`](impact_numbers.md). No price point is set until a pilot measures the lift; nothing here is a quote.
