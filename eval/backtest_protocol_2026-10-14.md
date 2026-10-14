# External backtest, fair-metrics protocol (pre-registered 2026-10-14)

This file is committed BEFORE any of the metrics, methods or variants below are run. Its sha256 is
recorded in the raw result file (`eval/raw/external_backtest_v2_2026-10-14.json`). Nothing here may be
changed after the run; anything learned later goes in `eval/external_backtest.md` as a new, dated note.

What was already known when this was written: the earlier "Baselines" section of
`eval/external_backtest.md` (sale-day WAPE and MAPE for Taal, seasonal-naive and the trailing 28-day
mean, pooled over all 8 origins). Nothing else below had been computed.

Scope: UCI Online Retail II, the committed 300-SKU sample, node = country, one cluster. Zero model
spend: local computation only, no Vertex or Gemini calls. The shipped forecaster
(`jobs/sense/forecast.py`) is not modified; every candidate is a backtest-only variant, labelled
"candidate, not shipped".

## 1. Origins: TUNE and REPORT

The 8 rolling origins (7 days apart, 7-day horizon, forecast days origin .. origin+6) are fixed by
`jobs.sense.backtest._origins`: 2011-10-14, 10-21, 10-28, 11-04, 11-11, 11-18, 11-25, 12-02.

- TUNE origins: the first four (2011-10-14, 10-21, 10-28, 11-04).
- REPORT origins: the last four (2011-11-11, 11-18, 11-25, 12-02).
- Any parameter choice and any variant selection uses TUNE origins only.
- Headline numbers use REPORT origins only. TUNE and all-8 numbers are also published, for transparency.
- Everything a method uses is dated strictly before its origin. Each method function filters its input
  to days < origin itself, and a unit test checks that rows at or after the origin are never read.
- A day with no row means no sale: 0 units.

## 2. Metrics

A "window" is one series at one origin (its 7 horizon days). A "pair" is a (series, origin) window.
Pairs are pooled within an origin group (TUNE, REPORT, ALL) unless stated.

1. **All-days WAPE (primary).** sum over all 7 horizon days of |forecast - actual| divided by sum of
   actual, zeros included. Pairs whose total actual over the 7-day window is 0 are excluded,
   identically for every method, and counted. (Sensitivity only, not a rule input: the same WAPE with no
   such exclusion.)
2. **Sale-day WAPE.** The old convention: only horizon days with actual > 0 are scored, WAPE pooled.
3. **MASE.** Per pair: mean absolute error over the 7 horizon days divided by the in-sample
   seasonal-naive-7 mean absolute error over the 28 days before the origin, i.e.
   mean over d in [O-28, O-1] of |y(d) - y(d-7)|. Pairs where that scale is 0 are excluded, identically for
   every method, and counted. Group value = mean of the per-pair MASE (the median is also published).
4. **Weekly-aggregate WAPE.** Per pair, forecasts over the 7 horizon days are summed to one number and
   compared with the summed actual; pooled WAPE = sum |F - A| / sum A over pairs with A > 0 (excluded
   pairs counted, same pairs as metric 1).
5. **Pooled bias.** sum(forecast - actual) / sum(actual) over the same slots as the all-days WAPE
   (negative = under-forecast). The sale-day bias is also published.
6. **MAPE (continuity only).** Mean over origins of the per-origin mean absolute percentage error over
   days with actual > 0, as `run_backtest` computes it. Flagged as unsuitable for intermittent demand:
   it ignores zero days and rewards low forecasts. It is never used in any decision rule.

A (series, origin) pair is also dropped for every method if the series' first sale is less than 28 days
before the origin (the existing rule; it dropped 0 pairs before).

**Fast-mover slice.** Pairs whose series had at least 15 sale days (days with a row) in the 28 days
before the origin. Every metric above is reported for this slice and for all pairs, for every method.

## 3. Methods

Unchanged / baselines:
- `taal`: `jobs.sense.forecast.SeriesModel.p50`, refit on days < origin, no promo or festival flag.
- `seasonal_naive`: units on the same weekday one week earlier.
- `mean28`: trailing 28 calendar days before the origin, no-sale days counted as 0, flat.
- `median28`: median of the same 28 zero-filled days, flat.
- `croston`: Croston's method with smoothing alpha on demand size z and on inter-demand interval p, run
  over the full history before the origin starting at the series' first sale day. Initial z = first
  demand size, initial p = 1. At each later demand day (units > 0) with q days since the previous one:
  z += alpha (y - z); p += alpha (q - p). Forecast = z / p, flat over the horizon.
- `sba`: Syntetos-Boylan approximation: (1 - alpha/2) * z / p, same recursion.
- alpha for `croston` and `sba` is chosen from the grid {0.05, 0.1, 0.2, 0.3} by lowest all-days WAPE on
  TUNE origins; the chosen alpha is then used unchanged on REPORT. The whole grid is published.

Candidate Taal variants ("candidate, not shipped"), each using only history before the origin. Let
`dow_k` be the weekday multiplier the shipped `SeriesModel` fits (shrunk 30% toward 1; flat 1.0 for
series it classes as intermittent) and `L0` the zero-filled mean units per calendar day over the 28
days before the origin.
- **V1** = `L0 * dow_k` for forecast weekday k (Taal's weekday shape, level per calendar day not per sale day).
- **V2** = 0.5 * V1 + 0.5 * `mean28`.
- **V3** = V1 with the multipliers shrunk 50% toward 1: `L0 * (0.5 * dow_k + 0.5)`.
- **V4** = `L0 * (0.5 * w_k + 0.5)` where `w_k` is a zero-filled weekday multiplier: mean units on weekday
  k over the last 91 days before the origin (zero days included) divided by the mean over those 91
  days (w_k = 1 if that mean is 0). Replaces the shipped sale-day weekday shape with one that counts
  days without a sale.
- **V5** = V1 with `L0` replaced by an exponentially weighted zero-filled mean over the 56 days before
  the origin, weight 0.5^(age/14) with age = days before the origin minus 1 (so half weight at 14 days).
  Tries to follow the pre-Christmas ramp.

No further variants and no other parameter values will be tried. V1..V5 are the complete list.

## 4. Decision rule

- The **primary candidate** is the variant of V1..V5 with the lowest TUNE all-days WAPE (ties broken by
  lower number). Only the primary candidate can be reported as an improvement; the others are reported
  descriptively.
- The primary candidate is reported as an improvement **only if** on the REPORT origins, all pairs, its
  all-days WAPE is lower than the unchanged Taal's AND lower than every baseline's (seasonal-naive,
  mean28, median28, croston, sba at the TUNE-chosen alpha). Otherwise the result says plainly that it does not.
- If it meets the rule, the margin is stated on REPORT, and TUNE, all-8, weekly WAPE, MASE, bias and the
  fast-mover slice are shown beside it; a metric where it is worse is stated.
- Taal (unchanged) is reported as beating or not beating each baseline on each metric on REPORT, all
  pairs and fast movers, with no tolerance band.
- A positive result is still one retailer, 8 weeks with a pre-Christmas ramp, 300 series; causes are
  readings consistent with the data, not proven.
