# Jobs

- `sense/`: forecasts (local seasonal model with regressors; `AI.FORECAST` + `ARIMA_PLUS_XREG` in BigQuery, SQL under `data/bigquery/sense`), gaps (five types, FIFO lot allocation, versioned sell-by rule), segments (k-means k=6), substitutes, copy. `python -m jobs.sense`. Spec §5.2; checklists `sense_forecasts.md`, `sense_gaps.md`, `segments_substitutes.md`.
- `measure/`: treated vs holdout per play in the play window, CI, `unmeasured` enforcement, priors update, food-waste line. `python -m jobs.measure`. Spec §5.7; checklist `measure.md`.

Both read and write the JSONL store in `TAAL_DATA_DIR`; on Google Cloud the same steps run as SQL in a Cloud Run Job (`infra/deploy.sh`).
