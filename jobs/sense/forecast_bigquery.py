"""AI.FORECAST (TimesFM) baseline forecast, run for real against BigQuery -- the bigquery_timesfm
option behind TAAL_FORECAST_BACKEND (jobs/sense/run.py). Runs the two committed SQL files
(02_forecast_timesfm.sql, then 04_rolldown.sql) against the real dataset and reads the resulting
node-level rows back, in the same shape jobs/sense/forecast.py::forecast() returns so
jobs/sense/gaps.py::detect() can consume either backend's output identically.

Two real, verified constraints (eval/raw/bigquery_ai_forecast_2026-09-27/):
- AI.FORECAST takes no covariate/regressor argument -- it produces the baseline only. The
  approve-time re-forecast and festival/promo effects stay on the local model (and, in
  BigQuery, on ARIMA_PLUS_XREG), never on this path.
- AI.FORECAST needs >=28 days of history per (sku, cluster_id) series or the INSERT fails with a
  null-timestamp error; 02_forecast_timesfm.sql filters to qualifying series for exactly this
  reason.

This module is never imported unless TAAL_FORECAST_BACKEND=bigquery_timesfm is explicitly set
(jobs/sense/run.py's own gate) -- importing google.cloud.bigquery unconditionally would break
every environment that runs the local forecaster, including CI.

By the time this function returns, 02_forecast_timesfm.sql and 04_rolldown.sql have already
INSERTed this run's rows into `taal.forecasts` for real -- this function's own SELECT is a
readback for jobs/sense/gaps.py::detect(), not the write path. Callers must NOT also write these
rows back through a store (see jobs/sense/run.py's own gate on this): agents/gate/bigquery_store.py's
`write()` used to be called unconditionally on this function's return value and, being a
tenant-wide DELETE, wiped every prior run's forecasts (real data loss, caught and fixed
2026-09-27 before it could reach a run against real data with billing enabled -- see
eval/raw/bigquery_forecast_dataloss_2026-09-27/).

The BigQuery Python client returns DATE columns as datetime.date and NUMERIC as Decimal; this
function converts both to the same plain str/float shapes jobs/sense/forecast.py::forecast()
already returns (its own `d.isoformat()`, `round(..., 3)`), so gaps.py::detect() and anything
else that consumes either backend's output sees one consistent row shape.
"""
from __future__ import annotations

import os
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

SQL_DIR = Path(__file__).resolve().parents[2] / "data" / "bigquery" / "sense"
MODEL = "timesfm"


def _json_safe_scalar(v: Any) -> Any:
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    if isinstance(v, Decimal):
        return float(v)
    return v


def _normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    return {k: _json_safe_scalar(v) for k, v in row.items()}


def forecast_bigquery(as_of: date, run_id: str, tenant_id: str, project: str | None = None, dataset: str | None = None) -> list[dict[str, Any]]:
    from google.cloud import bigquery

    proj = project or os.environ.get("GOOGLE_CLOUD_PROJECT", "amru-509214")
    # TAAL_BQ_DATASET matches agents.gate.bigquery_store.BigQueryStore's own selector -- a dry run
    # points both at the same throwaway dataset (e.g. taal_staging) without changing the default.
    dataset = dataset or os.environ.get("TAAL_BQ_DATASET", "taal")
    client = bigquery.Client(project=proj)
    params = [
        bigquery.ScalarQueryParameter("tenant_id", "STRING", tenant_id),
        bigquery.ScalarQueryParameter("as_of", "DATE", as_of.isoformat()),
        bigquery.ScalarQueryParameter("run_id", "STRING", run_id),
    ]
    for sql_file in ("02_forecast_timesfm.sql", "04_rolldown.sql"):
        sql = (SQL_DIR / sql_file).read_text(encoding="utf-8").replace("`taal.", f"`{proj}.{dataset}.")
        client.query(sql, job_config=bigquery.QueryJobConfig(query_parameters=params)).result()

    rows = list(client.query(
        f"SELECT * FROM `{proj}.{dataset}.forecasts` WHERE tenant_id = @tenant_id AND run_id = @run_id AND node_id IS NOT NULL",
        job_config=bigquery.QueryJobConfig(query_parameters=params),
    ).result())
    return [_normalize_row(dict(r)) for r in rows]
