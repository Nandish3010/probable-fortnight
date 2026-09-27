# Nightly Sense/Measure run records

One row per `make nightly-report` (harness/nightly_report.py). Every number is **measured**: a
live, read-only read of the Cloud Run Admin API, Cloud Logging and BigQuery at the time shown;
the full record is the JSON file named in the first column.

| report | sense (latest) | measure (latest) | green streak sense/measure | forecast rows node/cluster | forecast run_ids | as_of | sales_daily max(date) | gaps | plays / outcomes | rows stable vs previous |
|---|---|---|---|---|---|---|---|---|---|---|
