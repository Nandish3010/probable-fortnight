# Forecaster backtest on a public retail dataset (2026-10-09)

Everything else in `eval/` was measured on the seeded synthetic tenant, whose demand is drawn from
the same kind of seasonal-plus-noise process the forecaster fits. This is the first run on data
Taal's authors did not generate. Raw summary: [`eval/raw/external_backtest_2026-10-09.json`](raw/external_backtest_2026-10-09.json).

## Dataset

UCI **Online Retail II** (Chen 2012, [doi:10.24432/C5CG6D](https://doi.org/10.24432/C5CG6D),
[page](https://archive.ics.uci.edu/dataset/502/online+retail+ii), CC BY 4.0), downloaded without an
account from `https://archive.ics.uci.edu/static/public/502/online+retail+ii.zip`
(sha256 `572e36277c2390fbfde10664750731e0a86f55e33470d91919085f0408e67bfb`). 1,067,371 invoice lines,
2009-12-01 to 2011-12-09, a UK online gift-ware retailer.

**It is not grocery.** Dunnhumby "The Complete Journey" has no direct download (the source-files page
is a request form), so the next candidate on the list was taken. Many buyers are wholesalers, so
daily demand per SKU is lumpy. There is no expiry, no stock and no cost.

## Method

- `data/external/online_retail_ii/load.py build` (stdlib only) keeps real product codes
  (`12345` / `12345A`), nets same-day cancellations, sums to (date, SKU, country), keeps the top 300
  SKUs by units. The committed derived sample is 1.0 MB (`data/external/online_retail_ii/sample/`);
  the raw workbook is not committed.
- Taal shape: SKU = StockCode, node = country (43), one cluster, so the forecaster sees one series
  per SKU. A day with no sale has no row, as in the synthetic generator. Fields the dataset lacks
  are `None`, not filled in: category, unit cost, shelf life, is_food, expiry, on-hand stock, inbound,
  lead time, promo flag (`on_promo` is `False` = unknown, so the promo coefficient is never fitted).
- `uv run python -m harness.external_backtest` calls `jobs.sense.backtest.run_backtest` unchanged:
  rolling origin every 7 days, 7-day horizon, 8 origins (2011-10-14 to 2011-12-02), `SeriesModel`
  refit on data before each origin, MAPE over series-days with a sale (actual > 0). A second metric,
  pooled WAPE (sum of absolute errors over sum of actuals across the same scored series-days), is
  computed from the same slots by re-walking them (`slot_metrics`, which asserts it reproduces
  `run_backtest`'s MAPE) and is reported next to MAPE, never instead of it.
  `tests/unit/test_external_backtest.py` re-runs it from the committed sample and checks the numbers.

## Numbers

| | Real: Online Retail II | Synthetic tenant (seeded, recomputed; `synthetic_reference` in the raw JSON) |
|---|---|---|
| Series | 300 SKUs | SKU x cluster series, 9 category tiers |
| Origins | 8 | 7 |
| Mean MAPE over origins | **3.79** | 0.133 (tiers 0.107 to 0.221) |
| **WAPE** (pooled over scored series-days) | **0.83** | 0.113 |
| Mean bias | +3.50 | +0.023 |
| Scored series-days | 10,809 | 43,742 |
| Per-origin MAPE range | 3.20 to 4.32 | n/a |

- The synthetic column is recomputed from the seeded tenant in the current tree (seed 20260912) with
  the same code, so both metrics are comparable; its MAPE still equals the 20 Sep committed 0.133.
- Behind the 3.79: over 10,809 scored series-days the median absolute percentage error is 0.78, 42%
  of them exceed 100%, yet the mean forecast is 51.4 units/day against 53.2 actual. The mean is
  driven by days with small actuals (a few units) forecast against a level set by wholesale days;
  the level itself is about right.
- 64% of series-days in the backtest windows had a sale; the metric scores only those.
- Forecast stage on the full history (as of 2011-12-10): 245 of 300 series use the seasonal model,
  55 fall back to `average_demand_intermittent`.
- **Gap detector: 0 gaps, and none are computable.** Every gap type needs on-hand stock
  (`inventory_batches`), and `online_sellby_breach`, `expiry_writeoff`, `rebalance` and
  `slow_mover` also need an expiry date. The dataset has neither, so the detector ran on an empty
  inventory and returned 0 of each of the six types. No stock level or expiry was synthesised to get
  a count.

### Why MAPE and WAPE differ here

MAPE averages a ratio per series-day, so every scored day counts the same whatever its size: a day
with 2 units sold against a forecast of 20 contributes 900% and a day with 500 units sold against
520 contributes 4%. On lumpy wholesale demand many days are small and the forecast level is set by
the large days, so a minority of small-actual days drives the mean to 3.79 (42% of scored days
exceed 100% error, median 0.78). WAPE divides the total absolute error by the total units sold, so it
is weighted by volume and the small days barely move it: 0.83 means the daily SKU forecasts are off
by about 83% of the units actually sold. MAPE therefore says the forecaster often badly overshoots
quiet days; WAPE says how much volume it misplaces, and that is still poor (0.113 on the synthetic
tenant). The aggregate level is about right (mean forecast 51.4 against 53.2 actual units a day), so
the weakness is the daily shape of lumpy demand, not the level. Both metrics score only days with a
sale, so neither penalises forecasting a sale on a day with none.

## Caveats

- A MAPE of 3.79 and a WAPE of 0.83 say the forecaster is poor at daily, per-SKU prediction on lumpy wholesale demand.
  Whether grocery dark-store demand behaves better is untested here; this is evidence about the
  method on data it was not built around, not about the pilot.
- The synthetic figure is low partly because the generator draws demand from a process the model
  fits. The two numbers are not comparable accuracy claims; they bracket "easy" and "hard".
- The windows (Oct to early Dec 2011) include the pre-Christmas ramp. Like the synthetic run, the
  backtest applies no festival or promo flag, so the ramp is not modelled.
- Gross units with same-day cancellations netted; later returns are not netted. Unit price (GBP) is
  the units-weighted mean and is a selling price, not a cost, so no margin or rupee-at-stake figure
  is derived from this run.
