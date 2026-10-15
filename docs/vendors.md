# How this differs from named vendors

Moved from the README.

Taal differs by what it plans to, not by what it forecasts: the online sell-by cut-off, with a
holdout and a forecast write-back per play. We did not find these three together in any public
vendor documentation; that is a statement about public pages, not a claim about what vendors can
do.

Columns: (a) plans to an online sell-by cut-off; (b) holdout or control group on every promotion;
(c) the promotion is written back into the forecast as a covariate; (d) India or quick-commerce.
Vendor cells come from public pages and search results read on 2026-10-09; the Taal row cites
code and tests.

| | (a) Online sell-by | (b) Holdout | (c) Forecast write-back | (d) India / quick-commerce |
|---|---|---|---|---|
| **Taal** | Yes: each lot's `online_sellby_date` comes from the tenant's versioned rule (`agents/gate/sellby.py:24`), and a dark-store lot's deadline is that date, not expiry (`jobs/sense/gaps.py`, `deadline = sellby if ...`); `tests/unit/test_sellby.py`, `tests/unit/test_ingest.py` | Yes: `holdout_required` is one of the eight rules every play must pass (`agents/gate/guardrails.py:157`); tenant floor `min_holdout_fraction = 0.05`; `tests/unit/test_guardrails.py:98` | Yes: approve writes the play into `future_regressors` and re-forecasts the series (`services/api/approve.py:144`); `tests/sql/test_forecast.py:23` | Built for Indian quick-commerce dark stores; the tenant is seeded, no live retailer yet |
| Blue Yonder | Not verified | Not verified | Not verified | Partial |
| RELEX | Partial | Not verified | Partial | Partial |
| Wasteless | No | Not verified | Not verified | Not verified |
| Afresh | No | Not verified | Not verified | No |
| Flashfood | No | No | No | No |

**Yes / Partial / No** are our reading of the vendor pages (Partial: part of the criterion, or one
of its markets). **Not verified** means the public pages and search results were silent; it does not
mean the feature is absent, and enterprise suites keep deeper documentation behind sales access.
No for Wasteless means it prices in-store from the expiry date; for Afresh (store ordering
software) and Flashfood (a consumer surplus marketplace) it means a different product category,
not a gap in a competing planner. RELEX (c) is Yes for promotions and not verified for markdowns;
RELEX (d) is quick-commerce customers outside India (Getir, Flink), none found in India.

Pricing: enterprise planning suites are quote-based; we found no public per-store price.

Sources: [Blue Yonder](https://blueyonder.com/resources/automate-fresh-food-pricing-with-pricing-real-time),
[RELEX](https://www.relexsolutions.com/resources/markdown-optimization/)
([promotions](https://www.relexsolutions.com/resources/promotion-forecasting-and-replenishment/)),
[Wasteless](https://www.wasteless.com/), [Afresh](https://www.afresh.com/),
[Flashfood](https://www.flashfood.com/).
