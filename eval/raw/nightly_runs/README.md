# Nightly Sense/Measure run records

One row per `make nightly-report` (harness/nightly_report.py). Every number is **measured**: a
live, read-only read of the Cloud Run Admin API, Cloud Logging and BigQuery at the time shown;
the full record is the JSON file named in the first column.

| report | sense (latest) | measure (latest) | green streak sense/measure | forecast rows node/cluster | forecast run_ids | as_of | sales_daily max(date) | gaps | plays / outcomes | rows stable vs previous |
|---|---|---|---|---|---|---|---|---|---|---|
| [2026-09-28.json](2026-09-28.json) | red 2026-09-27T20:00:10.795254Z (12.1s) | no executions | 0/0 | 0/50708 | 4 | 2026-09-12 | 2026-09-11 | 0 | 0 / 0 | n/a (first report) |
