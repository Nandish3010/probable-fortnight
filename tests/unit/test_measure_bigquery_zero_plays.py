"""Nightly Measure against the BigQuery store with zero plays (DECISIONS §5.6/§5.7).

Judge-mode approvals live in per-visitor sandboxes and never reach BigQuery, so the nightly
taal-measure job normally finds nothing to measure. That must be one explicit log line and a
clean exit, not a silent no-op rewrite of play_outcomes/estimator_priors/plays. No network: the
BigQuery-backed tables are faked, everything else is the seeded local snapshot.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from agents.gate.bigquery_store import BIGQUERY_TABLES, BigQueryStore
from jobs.measure import run as measure_run


class _EmptyBigQueryStore(BigQueryStore):
    def __init__(self, root):
        super().__init__(root)
        self.write_calls: list[str] = []

    def read(self, table):
        if table in BIGQUERY_TABLES:
            return []
        return super().read(table)

    def write(self, table, rows):
        self.write_calls.append(table)


@pytest.fixture
def empty_bq_store(data_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> _EmptyBigQueryStore:
    isolated = tmp_path / "data"
    shutil.copytree(data_dir, isolated)
    store = _EmptyBigQueryStore(str(isolated))
    monkeypatch.setattr(measure_run, "build_batch_store", lambda data_dir: store)
    return store


def test_zero_plays_in_bigquery_logs_the_reason_and_writes_nothing(empty_bq_store, capsys):
    out = measure_run.run_measure(empty_bq_store.root, computed_at="2026-09-28T20:30:00Z")
    assert out["plays"] == 0 and out["measured"] == 0 and out["note"] == measure_run.NO_PLAYS_IN_BIGQUERY
    assert capsys.readouterr().out.strip().splitlines() == [measure_run.NO_PLAYS_IN_BIGQUERY]
    assert empty_bq_store.write_calls == []


def test_main_exits_zero_with_zero_plays(empty_bq_store, capsys):
    assert measure_run.main(["--data", str(empty_bq_store.root)]) == 0
    assert measure_run.NO_PLAYS_IN_BIGQUERY in capsys.readouterr().out


def test_sentence_matches_architecture_doc():
    doc = (Path(__file__).resolve().parents[2] / "docs" / "architecture.md").read_text(encoding="utf-8")
    assert measure_run.NO_PLAYS_IN_BIGQUERY in " ".join(doc.split())
