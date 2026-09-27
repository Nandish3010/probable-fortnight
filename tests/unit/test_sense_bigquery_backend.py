"""jobs/sense/run.py's TAAL_FORECAST_BACKEND/TAAL_BATCH_STORE selection, specifically the
2026-09-27 data-loss fix: with TAAL_FORECAST_BACKEND=bigquery_timesfm, 02_forecast_timesfm.sql
and 04_rolldown.sql have already INSERTed this run's rows into taal.forecasts for real, so
run_sense() must NOT also call store.write("forecasts", rows) -- that used to re-run
BigQueryStore.write()'s own tenant-wide delete-then-load on a table that already had these exact
rows, wiping every other run's forecast history in the process (real data loss, found and fixed
before it ever ran against a project with billing enabled).

Local backend behaviour (the default everywhere) must stay byte-for-byte unchanged: store.write
is still called with the local forecaster's rows.
"""
from __future__ import annotations

import shutil
from datetime import date
from pathlib import Path

import pytest

from agents.gate.store import LocalStore
from jobs.sense import run as sense_run


class _SpyStore(LocalStore):
    def __init__(self, root):
        super().__init__(root)
        self.write_calls: list[tuple[str, list]] = []

    def write(self, table, rows):
        rows = list(rows)
        self.write_calls.append((table, rows))
        return super().write(table, rows)


@pytest.fixture
def spy_store(data_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> _SpyStore:
    # data_dir is a SESSION-scoped fixture that returns the real, shared .local/data once it
    # exists -- this test calls run_sense(), which writes gaps/style_trends/etc. back through the
    # store, so it must run against its own throwaway copy, never the shared fixture directory
    # other tests (tests/sql especially) depend on staying at its generated values.
    isolated = tmp_path / "data"
    shutil.copytree(data_dir, isolated)
    spy = _SpyStore(str(isolated))
    monkeypatch.setattr(sense_run, "build_batch_store", lambda data_dir: spy)
    return spy


def test_local_backend_writes_forecasts_through_store_unchanged(spy_store, monkeypatch):
    monkeypatch.delenv("TAAL_FORECAST_BACKEND", raising=False)
    monkeypatch.delenv("TAAL_BATCH_STORE", raising=False)
    record = sense_run.run_sense(spy_store.root, as_of=date(2026, 9, 12))
    forecast_writes = [rows for table, rows in spy_store.write_calls if table == "forecasts"]
    assert len(forecast_writes) == 1, "the local backend must still write its own forecast rows through store.write()"
    assert forecast_writes[0] and forecast_writes[0][0]["model"] == "local_seasonal_xreg"
    assert record["model"] == "local_seasonal_xreg"


def test_bigquery_timesfm_backend_never_rewrites_forecasts_through_store(spy_store, monkeypatch):
    fake_rows = [
        {"tenant_id": "kutumb-mart", "run_id": "ai_forecast_timesfm_20261001", "sku": "S1", "node_id": "DS-01", "cluster_id": "C1", "date": "2026-10-01", "p10": 1.0, "p50": 2.0, "p90": 3.0, "model": "timesfm", "method": "ai_forecast_timesfm", "includes_plays": False, "as_of": "2026-09-12"},
    ]

    def fake_forecast_bigquery(as_of, run_id, tenant_id, **kw):
        return fake_rows

    monkeypatch.setattr("jobs.sense.forecast_bigquery.forecast_bigquery", fake_forecast_bigquery)
    monkeypatch.setenv("TAAL_FORECAST_BACKEND", "bigquery_timesfm")
    monkeypatch.delenv("TAAL_BATCH_STORE", raising=False)

    record = sense_run.run_sense(spy_store.root, as_of=date(2026, 9, 12))

    forecast_writes = [rows for table, rows in spy_store.write_calls if table == "forecasts"]
    assert forecast_writes == [], "bigquery_timesfm rows are already persisted by 02/04.sql -- store.write('forecasts', ...) must never be called for this backend"
    # gaps/style_trends still go through the store as normal -- this backend only changes the
    # forecasts write, nothing else about run_sense's own bookkeeping
    assert any(table == "gaps" for table, _ in spy_store.write_calls)
    assert record["model"] == "timesfm"
    assert record["forecast_rows"] == 1
