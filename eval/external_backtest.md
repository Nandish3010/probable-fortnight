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

## Baselines (added 2026-10-14)

The 0.83 and 3.79 above had nothing next to them. Two naive baselines were scored on exactly the same
series-days with the same scoring function. Raw numbers, method definitions and input hashes:
[`eval/raw/external_backtest_baselines_2026-10-14.json`](raw/external_backtest_baselines_2026-10-14.json);
code: `uv run python -m harness.external_backtest --baselines --date 2026-10-14` (deterministic, no
random component, no network, no model calls); `tests/unit/test_external_backtest_baselines.py`
checks both baselines against hand-computed values and checks that the committed numbers reproduce.

| Method | WAPE (pooled) | Mean MAPE over origins | Scored series-days |
|---|---|---|---|
| Taal forecaster (`SeriesModel`, unchanged) | **0.826** | **3.786** | 10,809 |
| Seasonal-naive (same weekday last week) | 0.979 | 2.939 | 10,809 |
| Trailing 28-day mean (flat, 28 calendar days before the origin) | **0.739** | **2.428** | 10,809 |

- **Same protocol for all three.** 300 SKU series, 8 rolling origins 7 days apart (2011-10-14 to
  2011-12-02), 7-day horizon (forecast days origin .. origin+6). Train/test boundary: for each origin
  O everything a method uses is dated strictly before O; the scored days are O to O+6. Scored only
  where actual units > 0 (a day with no sale is not scored, for every method). Taal's row reproduces
  the headline figures above (WAPE 0.8260 and 10,809 series-days; MAPE 3.7861 against 3.79).
- **No look-ahead.** Seasonal-naive reads day d-7, which is always before the origin for a 7-day horizon;
  the 28-day mean reads days O-28 to O-1 only. A day with no row counts as 0 units for both, because
  that is what a day with no row means in this data.
- **Exclusions: 0.** A (series, origin) would have been dropped for all three methods if the series'
  first sale fell less than 28 days before the origin (no full last-week or 28-day window yet). None
  did: all 2,400 series-origin pairs were scored by all three methods.
- **MAPE is the existing convention** (mean over origins of the per-origin mean absolute percentage
  error); the WAPE and MAPE columns are pooled over the same 10,809 series-days.
- **What the table says.** On WAPE Taal is 15.7% lower than seasonal-naive (0.826 against 0.979) and
  11.8% higher than the trailing 28-day mean (0.826 against 0.739). On MAPE Taal is higher than both
  baselines (3.79 against 2.94 and 2.43). **Taal does not beat both baselines on this dataset, so this
  result is not promoted to the README table.** It beats last-week-same-day on volume-weighted error
  only, and loses to a flat 28-day average on both metrics.
- **Why a flat mean wins here (consistent with the data, not separately proven).** Weekday structure
  carries little signal in lumpy wholesale demand, so seasonal-naive is noisy. `SeriesModel` sets its
  level from days that had a sale only, while the trailing mean divides by all 28 days; a sensitivity
  variant that also averages only over days with a sale (raw JSON, `trailing_28d_mean_sale_days_only`)
  scores WAPE 0.816 and MAPE 3.688, about 1% and 3% below Taal. Because only days with a sale are scored,
  methods that forecast lower do better on this metric: pooled bias (sum of forecast minus actual,
  over total actual) is -0.30 for the 28-day mean, -0.13 for seasonal-naive and -0.03 for Taal.
- This is one retailer, one 8-week window and one scoring rule; it says nothing about grocery
  dark-store demand, which remains untested here.

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

## Fair metrics and candidates (added 2026-10-14)

The Baselines section scored only days with a sale, which rewards low forecasts on lumpy demand. This
section re-scores the same series and origins with zeros counted, on a protocol fixed before the run:
[`eval/backtest_protocol_2026-10-14.md`](backtest_protocol_2026-10-14.md) (committed first; its sha256 is
in the raw file). Raw results: [`eval/raw/external_backtest_v2_2026-10-14.json`](raw/external_backtest_v2_2026-10-14.json);
code: `uv run python -m harness.external_backtest --fair --date 2026-10-14` (deterministic, local, no model
calls, about 4 seconds); tests: `tests/unit/test_external_backtest_fair.py` (Croston, SBA, MASE scaling,
weekly aggregation and the candidates against hand-computed values; no method reads a day at or after
its origin; the committed numbers reproduce). `jobs/sense/forecast.py` is unchanged.

**Protocol in one paragraph.** The 8 origins are split: the first 4 (2011-10-14 to 2011-11-04) are TUNE,
the last 4 (2011-11-11 to 2011-12-02) are REPORT. Choices (Croston and SBA smoothing alpha from
{0.05, 0.1, 0.2, 0.3}; which candidate is "primary") use TUNE only; the headline is REPORT. A window is
one SKU at one origin (7 days). All-days WAPE counts zero days and drops windows with no sale at all
(108 of 1,200 per group, the same for every method); MASE is scaled by the in-sample seasonal-naive-7
error over the 28 days before the origin (windows with scale 0 dropped, same for every method: 72 TUNE,
76 REPORT; fast movers have none); weekly WAPE sums each SKU's 7 days first. "Fast movers" are windows
whose SKU sold on at least 15 of the 28 days before the origin (892 TUNE, 941 REPORT windows). MAPE is shown for
continuity only. The earlier sale-day numbers reproduce on all 8 origins (Taal sale-day WAPE 0.826,
MAPE 3.786, 10,809 series-days; `results.ALL` in the raw file).

Chosen alpha: 0.05 for both Croston and SBA (the smallest in the grid, so the grid's edge: a smaller
value was not tried and might do slightly better). V2 and V3 are algebraically identical
(0.5 x V1 + 0.5 x mean28 equals V1 with the multipliers halfway to 1), so their columns match; that was an
oversight in the protocol and they count as one variant. The pre-registered primary candidate (lowest
TUNE all-days WAPE) is **V4**. Lower is better in every table below except bias, where 0 is best.

**All-days WAPE (zeros included; lower is better)**

| Method | TUNE, all | REPORT, all | TUNE, fast movers | REPORT, fast movers |
|---|---|---|---|---|
| Taal SeriesModel (unchanged) | 1.325 | 1.119 | 1.103 | 0.970 |
| Seasonal-naive | 1.132 | 0.993 | 1.107 | 0.963 |
| Trailing 28-day mean | 1.007 | 0.907 | 0.982 | 0.884 |
| Trailing 28-day median | 0.883 | 0.818 | 0.865 | 0.805 |
| Croston (alpha 0.05) | 1.000 | 0.890 | 0.964 | 0.865 |
| SBA (alpha 0.05) | 0.993 | 0.883 | 0.957 | 0.859 |
| V1 (candidate, not shipped) | 0.990 | 0.882 | 0.962 | 0.858 |
| V2 (candidate, not shipped) | 0.996 | 0.892 | 0.969 | 0.868 |
| V3 (candidate, not shipped) | 0.996 | 0.892 | 0.969 | 0.868 |
| V4 (candidate, not shipped) | 0.966 | 0.857 | 0.938 | 0.831 |
| V5 (candidate, not shipped) | 0.990 | 0.877 | 0.962 | 0.852 |

**Sale-day WAPE (the earlier convention)**

| Method | TUNE, all | REPORT, all | TUNE, fast movers | REPORT, fast movers |
|---|---|---|---|---|
| Taal SeriesModel (unchanged) | 0.869 | 0.788 | 0.826 | 0.753 |
| Seasonal-naive | 1.034 | 0.932 | 1.026 | 0.917 |
| Trailing 28-day mean | 0.771 | 0.712 | 0.764 | 0.703 |
| Trailing 28-day median | 0.792 | 0.726 | 0.760 | 0.706 |
| Croston (alpha 0.05) | 0.771 | 0.704 | 0.760 | 0.696 |
| SBA (alpha 0.05) | 0.770 | 0.702 | 0.758 | 0.694 |
| V1 (candidate, not shipped) | 0.770 | 0.703 | 0.763 | 0.694 |
| V2 (candidate, not shipped) | 0.768 | 0.705 | 0.761 | 0.696 |
| V3 (candidate, not shipped) | 0.768 | 0.705 | 0.761 | 0.696 |
| V4 (candidate, not shipped) | 0.787 | 0.727 | 0.783 | 0.717 |
| V5 (candidate, not shipped) | 0.764 | 0.696 | 0.759 | 0.687 |

**MASE, mean of per-window values (lower is better; scale = in-sample seasonal-naive-7 error)**

| Method | TUNE, all | REPORT, all | TUNE, fast movers | REPORT, fast movers |
|---|---|---|---|---|
| Taal SeriesModel (unchanged) | 6.823 | 9.308 | 1.183 | 1.104 |
| Seasonal-naive | 1.319 | 1.502 | 1.161 | 1.136 |
| Trailing 28-day mean | 1.224 | 1.358 | 1.054 | 1.004 |
| Trailing 28-day median | 1.110 | 1.267 | 0.965 | 0.928 |
| Croston (alpha 0.05) | 1.662 | 1.839 | 1.055 | 0.998 |
| SBA (alpha 0.05) | 1.643 | 1.819 | 1.048 | 0.991 |
| V1 (candidate, not shipped) | 1.213 | 1.341 | 1.040 | 0.983 |
| V2 (candidate, not shipped) | 1.216 | 1.347 | 1.044 | 0.991 |
| V3 (candidate, not shipped) | 1.216 | 1.347 | 1.044 | 0.991 |
| V4 (candidate, not shipped) | 1.181 | 1.308 | 1.006 | 0.948 |
| V5 (candidate, not shipped) | 1.256 | 1.385 | 1.048 | 0.985 |

**MASE, median of per-window values**

| Method | TUNE, all | REPORT, all | TUNE, fast movers | REPORT, fast movers |
|---|---|---|---|---|
| Taal SeriesModel (unchanged) | 1.049 | 0.975 | 0.961 | 0.916 |
| Seasonal-naive | 0.865 | 0.957 | 0.928 | 0.960 |
| Trailing 28-day mean | 0.768 | 0.770 | 0.790 | 0.778 |
| Trailing 28-day median | 0.647 | 0.684 | 0.695 | 0.700 |
| Croston (alpha 0.05) | 0.821 | 0.784 | 0.800 | 0.777 |
| SBA (alpha 0.05) | 0.813 | 0.776 | 0.789 | 0.772 |
| V1 (candidate, not shipped) | 0.756 | 0.748 | 0.784 | 0.751 |
| V2 (candidate, not shipped) | 0.758 | 0.757 | 0.783 | 0.767 |
| V3 (candidate, not shipped) | 0.758 | 0.757 | 0.783 | 0.767 |
| V4 (candidate, not shipped) | 0.741 | 0.724 | 0.757 | 0.725 |
| V5 (candidate, not shipped) | 0.797 | 0.774 | 0.805 | 0.772 |

**Weekly-aggregate WAPE (each SKU's 7 days summed)**

| Method | TUNE, all | REPORT, all | TUNE, fast movers | REPORT, fast movers |
|---|---|---|---|---|
| Taal SeriesModel (unchanged) | 0.874 | 0.674 | 0.662 | 0.530 |
| Seasonal-naive | 0.687 | 0.546 | 0.665 | 0.522 |
| Trailing 28-day mean | 0.601 | 0.472 | 0.569 | 0.452 |
| Trailing 28-day median | 0.656 | 0.558 | 0.606 | 0.526 |
| Croston (alpha 0.05) | 0.602 | 0.458 | 0.565 | 0.442 |
| SBA (alpha 0.05) | 0.599 | 0.458 | 0.562 | 0.442 |
| V1 (candidate, not shipped) | 0.597 | 0.471 | 0.564 | 0.451 |
| V2 (candidate, not shipped) | 0.599 | 0.472 | 0.567 | 0.451 |
| V3 (candidate, not shipped) | 0.599 | 0.472 | 0.567 | 0.451 |
| V4 (candidate, not shipped) | 0.601 | 0.472 | 0.569 | 0.452 |
| V5 (candidate, not shipped) | 0.585 | 0.455 | 0.553 | 0.435 |

**Pooled bias on all days, (forecast - actual) / actual (0 is best)**

| Method | TUNE, all | REPORT, all | TUNE, fast movers | REPORT, fast movers |
|---|---|---|---|---|
| Taal SeriesModel (unchanged) | +0.367 | +0.344 | +0.173 | +0.202 |
| Seasonal-naive | -0.129 | +0.008 | -0.108 | +0.025 |
| Trailing 28-day mean | -0.128 | -0.051 | -0.101 | -0.036 |
| Trailing 28-day median | -0.598 | -0.479 | -0.538 | -0.442 |
| Croston (alpha 0.05) | -0.172 | -0.119 | -0.156 | -0.115 |
| SBA (alpha 0.05) | -0.193 | -0.141 | -0.177 | -0.137 |
| V1 (candidate, not shipped) | -0.146 | -0.070 | -0.122 | -0.057 |
| V2 (candidate, not shipped) | -0.137 | -0.060 | -0.112 | -0.046 |
| V3 (candidate, not shipped) | -0.137 | -0.060 | -0.112 | -0.046 |
| V4 (candidate, not shipped) | -0.128 | -0.051 | -0.101 | -0.036 |
| V5 (candidate, not shipped) | -0.122 | -0.067 | -0.100 | -0.056 |

**MAPE, continuity only (unsuitable for intermittent demand)**

| Method | TUNE, all | REPORT, all | TUNE, fast movers | REPORT, fast movers |
|---|---|---|---|---|
| Taal SeriesModel (unchanged) | 3.966 | 3.607 | 3.441 | 3.195 |
| Seasonal-naive | 2.893 | 2.985 | 2.927 | 2.987 |
| Trailing 28-day mean | 2.494 | 2.362 | 2.548 | 2.418 |
| Trailing 28-day median | 1.188 | 1.165 | 1.214 | 1.181 |
| Croston (alpha 0.05) | 2.426 | 2.296 | 2.452 | 2.324 |
| SBA (alpha 0.05) | 2.364 | 2.236 | 2.388 | 2.263 |
| V1 (candidate, not shipped) | 2.412 | 2.273 | 2.461 | 2.322 |
| V2 (candidate, not shipped) | 2.450 | 2.314 | 2.501 | 2.366 |
| V3 (candidate, not shipped) | 2.450 | 2.314 | 2.501 | 2.366 |
| V4 (candidate, not shipped) | 2.704 | 2.481 | 2.763 | 2.537 |
| V5 (candidate, not shipped) | 2.463 | 2.295 | 2.494 | 2.341 |

**Does unchanged Taal beat each baseline? REPORT origins, all series (yes = lower error; for bias, closer to 0)**

| Metric | Seasonal-naive | 28-day mean | 28-day median | Croston | SBA |
|---|---|---|---|---|---|
| All-days WAPE | no | no | no | no | no |
| Sale-day WAPE | yes | no | no | no | no |
| MASE (mean) | no | no | no | no | no |
| MASE (median) | no | no | no | no | no |
| Weekly WAPE | no | no | no | no | no |
| Absolute bias | no | no | yes | no | no |
| MAPE (continuity) | no | no | no | no | no |

**Does unchanged Taal beat each baseline? REPORT origins, fast movers (yes = lower error; for bias, closer to 0)**

| Metric | Seasonal-naive | 28-day mean | 28-day median | Croston | SBA |
|---|---|---|---|---|---|
| All-days WAPE | no | no | no | no | no |
| Sale-day WAPE | yes | no | no | no | no |
| MASE (mean) | yes | no | no | no | no |
| MASE (median) | yes | no | no | no | no |
| Weekly WAPE | no | no | no | no | no |
| Absolute bias | no | no | yes | no | no |
| MAPE (continuity) | no | no | no | no | no |


**Pre-registered rule, REPORT origins, all series, all-days WAPE.** Primary candidate V4 (candidate, not
shipped): 0.857. Unchanged Taal: 1.119 (V4 lower by 0.262, 23%). Baselines: seasonal-naive 0.993,
28-day mean 0.907, SBA 0.883, Croston 0.890, **28-day median 0.818**. V4 beats Taal and four of the five
baselines but **not the 28-day median (0.818 against 0.857, V4 worse by 0.039), so the rule is not met and
no candidate is reported as an improvement.** V1, V2/V3 and V5 also beat Taal and miss the median.
(Read with the bias table: the median's lead is bought with a bias of -0.48, see below.)

**Post-hoc reading aids** (written after the first run, not inputs to any rule; `post_hoc_diagnostics` in
the raw file). REPORT windows with a sale:

| | Taal | 28-day mean | V1 | V4 |
|---|---|---|---|---|
| Forecast units on Saturdays (actual: 0, the retailer takes no Saturday orders) | 54,754 | 41,806 | 37,395 | 20,903 |
| All-days WAPE with Saturdays removed | 0.941 | 0.771 | 0.761 | 0.789 |
| All-days WAPE, 231 windows where Taal uses its sparse-series fallback | 3.367 (bias +2.54) | 1.201 (bias -0.26) | 1.201 | 1.191 |
| All-days WAPE, 969 windows on Taal's seasonal model | 0.979 (bias +0.21) | 0.889 (bias -0.04) | 0.862 | 0.836 |

## Reading

- **Counting zeros changes the picture.** On days with a sale, Taal's REPORT bias is +0.013 (about
  right); over all days it is +0.344, i.e. it forecasts about a third more units than were sold. Taal
  sets its level from days with a sale, so it forecasts "a day when something sells" on every day; the
  trailing mean divides by calendar days. On all-days WAPE unchanged Taal (1.119) loses to every
  baseline, including seasonal-naive (0.993), where it had won on sale-day WAPE (0.788 against 0.932).
  Taal beats a baseline on a metric only in the "yes" cells above: seasonal-naive on sale-day WAPE
  (all series and fast movers) and on MASE for fast movers, and the 28-day median on absolute bias. It
  does not beat the 28-day mean, Croston or SBA on any metric, in either slice.
- **Fast movers narrow the gap but do not close it.** All-days WAPE REPORT: Taal 0.970, seasonal-naive 0.963,
  28-day mean 0.884, Croston 0.865, SBA 0.859, median 0.805. Taal's fast-mover bias is +0.202.
- **Where the excess error sits (consistent with the data, not separately proven).** The 231 REPORT windows
  where Taal drops to its sparse-series fallback score 3.37 with bias +2.54: that fallback uses the mean
  of every sale-day row in the whole history as its level, which overstates a series that has since faded.
  On the 969 windows on the seasonal model Taal is 0.979, still above the 28-day mean's 0.889 with bias +0.21.
  Taal also forecasts 54,754 units on Saturdays, a weekday with zero sales in the window (the
  retailer takes no Saturday orders); its weekday shape cannot see a day with no rows. Removing Saturdays
  lowers Taal to 0.941, still well above the 28-day mean (0.771), so the closed day is part of the story,
  not all of it.
- **Does Taal's weekday shape add value over a flat level?** A little, once the level is zero-filled. V1 (Taal's
  multipliers on the zero-filled level) scores 0.882 on REPORT and 0.990 on TUNE against 0.907 and 1.007 for the
  flat 28-day mean (2.8% and 1.7% lower); fast movers 0.858 against 0.884; weekly WAPE and sale-day WAPE are
  within 0.001 and 0.009. Halving the multipliers (V2/V3) gives 0.892, in between. A weekday shape
  that counts days without a sale (V4) does better, 0.857 REPORT and 0.966 TUNE, but is worse on sale-day WAPE
  (0.727 against 0.712) and MAPE, because it forecasts less on the days that had sales. Following the
  ramp with an exponentially weighted level (V5) adds almost nothing over V1 (0.877 against 0.882 REPORT,
  0.990 against 0.990 TUNE). Croston and SBA are no better than a flat zero-filled mean here (0.883 to 0.890
  against 0.907 on REPORT, no better than V1) and have the highest MASE mean of the non-Taal methods (1.8), so the extra machinery does not pay.
- **Why the median "wins" and why that is not a useful win.** A 28-day median over zero-filled days is 0 for
  most intermittent series, so it forecasts zero on most days. Absolute-error metrics are minimised by the
  median, so it scores best on all-days WAPE and MASE median (0.818, 0.684) while under-forecasting by 48% (bias
  -0.479) and worse than seasonal-naive on weekly WAPE (0.558 against 0.546; 0.455 to 0.472 for V5, Croston, SBA, V1, V4 and the mean). The
  rule counted it as a baseline as written; a forecast that is mostly zero cannot drive replenishment.
  Against the other four baselines V4 is ahead (0.857 against 0.883 to 0.993), but that comparison is
  post-hoc and does not satisfy the pre-registered rule.
- **The MASE mean is dominated by outliers for Taal** (REPORT mean 9.3 against median 0.975): a few windows
  with a near-zero in-sample scale. Read the median beside it.

**Limits.** One retailer (UK gift-ware, many wholesale buyers, no Saturday orders), 8 weekly origins with a
pre-Christmas ramp (REPORT is the 4 weeks nearest Christmas, so any level-only method under-forecasts there),
300 series, one 4-origin REPORT window per number: differences in the third decimal are noise. The causes
above are readings consistent with the numbers, not proven. Dark-store demand is not tested here. The
candidates are backtest-only and not shipped; no promo or festival flag is used (the dataset has none).
