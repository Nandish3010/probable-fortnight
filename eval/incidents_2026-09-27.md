# BigQuery batch path: incidents of 27 Sep 2026

Moved verbatim from README 'What is real, what is simulated' on 27 Sep 2026.

**Forecasting and the nightly batch split, stated once here** (the same wording appears in
`docs/architecture.md`, `docs/scale.md`, `infra/README.md`): the judge-mode serving path
(`taal-agents`, this app) always reads a frozen, pinned-clock local snapshot and never touches
BigQuery directly -- what a judge clicks never depends on a nightly job having run. Behind that,
`jobs/sense` and `jobs/measure` support two backends, selected by env vars that default to the
local path everywhere except the `taal-sense`/`taal-measure` Cloud Run Jobs' own environment:
`TAAL_FORECAST_BACKEND=local` (the pure-Python forecaster) or `bigquery_timesfm`, which runs
BigQuery `AI.FORECAST` (TimesFM) for real; `TAAL_BATCH_STORE=local` (JSONL) or `bigquery`, which
writes through `agents/gate/bigquery_store.py::BigQueryStore`. `AI.FORECAST` was verified live
against project `amru-509214` in `asia-south1`: available, no covariate/regressor parameter
(confirmed by a real rejection), a real SQL bug found and fixed, and a full run across all 895
qualifying series (25,060 rows, ~23s, ~70MB billed) -- evidence in
`eval/raw/bigquery_ai_forecast_2026-09-27/`. A head-to-head backtest against the local model, same
rolling origins as `jobs/sense/backtest.py`, found the local model with lower MAPE in every one of
45 (origin, tier) comparisons -- expected, since the seeded data was generated with the same form
the local model fits; see `head_to_head_summary.json` in that directory. **A billing/payment issue
on the GCP project briefly blocked all BigQuery writes on 2026-09-27** (DML, streaming inserts and
load jobs all failed with `billingNotEnabled` for roughly the 15:31-15:33 UTC window and after);
this has since been resolved by the project owner and re-verified live, twice, over an hour apart
(streaming insert, DML `INSERT`/`DELETE`, `LOAD`, `CREATE TABLE` and `DROP TABLE` all succeeding
cleanly). No data was lost during the outage. **A separate, real data-loss bug was found and fixed
the same day** (before it ever ran against a project with billing enabled): `BigQueryStore.write()`
used a tenant-wide `DELETE` even on `forecasts`, a history table, which would have wiped every
prior run's rows on the very next nightly write; `run.py` also unconditionally re-wrote `forecasts`
through that path even when the `bigquery_timesfm` backend had already persisted the same rows via
real SQL `INSERT`s. Fixed: `run.py` no longer re-writes `forecasts` for the `bigquery_timesfm`
backend; `BigQueryStore.write()` now scopes `forecasts` deletes to `(tenant_id, run_id)` (never
tenant-wide), stages new rows in a throwaway table and swaps them in via a single `BEGIN
TRANSACTION`/`COMMIT TRANSACTION` script, so a failed load or swap always leaves the existing rows
untouched; date/Decimal values are made JSON-safe before any load. `load_table_from_json` with
`WRITE_TRUNCATE` into an existing table was also found to silently reorder and drop nested
`STRUCT` subfields when no explicit schema is passed -- fixed by always passing the real, fetched
target schema. Evidence, tests and the full bug chain: `eval/raw/bigquery_forecast_dataloss_2026-09-27/`,
`tests/unit/test_bigquery_store.py`, `tests/unit/test_sense_bigquery_backend.py`.

**The `taal.gaps` DDL/code mismatch this uncovered has been migrated live and re-verified**:
`evidence` was missing not just `counterpart_gap_id` (rebalance gaps) but 14 more fields
`jobs/sense/gaps.py` has always emitted for online_sellby_breach/expiry_writeoff, stockout_risk,
slow_mover, unmet_demand and assortment_gap gaps -- roughly 80% of all gaps by volume. All 15
fields are now live on `taal.gaps` (additive, nullable; no field dropped, renamed or retyped), and
`infra/deploy.sh` gained a permanent, idempotent migration step so a fresh deploy never falls
behind the DDL again. **The nightly BigQuery batch path (`TAAL_BATCH_STORE=bigquery`,
`TAAL_FORECAST_BACKEND=bigquery_timesfm`) is now verified against a staging clone of `taal`**: a
full `jobs.sense` run against `taal_staging` succeeded end-to-end (533 gaps across all 6 real gap
types, all 7 rebalance gaps carrying `counterpart_gap_id`, prior forecast runs untouched). It has
not yet been run for real against `taal` itself -- see
`eval/raw/bigquery_schema_migration_2026-09-27/finding.json` for the full migration record and
`eval/raw/bigquery_billing_dml_2026-09-27/finding.json` for the billing timeline.
