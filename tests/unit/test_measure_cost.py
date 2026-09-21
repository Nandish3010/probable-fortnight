"""jobs.measure.cost: pure-logic tests that never touch real GCP credentials or network (that
part is exercised live and recorded under eval/raw/cost_measurement_*.json -- see
eval/evaluation.md).
"""
import pytest

from jobs.measure import cost as cost_module


class _FakeDataset:
    def __init__(self, dataset_id):
        self.dataset_id = dataset_id


class _FakeTable:
    def __init__(self, table_id):
        self.table_id = table_id


class _FakeClient:
    project = "proj"

    def __init__(self, tables_by_dataset):
        self._tables_by_dataset = tables_by_dataset

    def list_datasets(self):
        return [_FakeDataset(d) for d in self._tables_by_dataset]

    def list_tables(self, dataset_id):
        return [_FakeTable(t) for t in self._tables_by_dataset[dataset_id]]


def test_find_billing_export_table_none_when_absent():
    client = _FakeClient({"taal": ["plays", "gaps", "products"]})
    assert cost_module.find_billing_export_table(client) is None


def test_find_billing_export_table_found_by_prefix():
    client = _FakeClient({"taal": ["plays"], "billing": ["gcp_billing_export_v1_01AFA8_481EFC_C09462"]})
    found = cost_module.find_billing_export_table(client)
    assert found == "proj.billing.gcp_billing_export_v1_01AFA8_481EFC_C09462"


def test_find_billing_export_table_resource_variant():
    client = _FakeClient({"billing": ["gcp_billing_export_resource_v1_01AFA8_481EFC_C09462"]})
    assert cost_module.find_billing_export_table(client) is not None


def test_run_cost_measurement_blocked_when_no_export(monkeypatch):
    monkeypatch.setattr(cost_module, "find_billing_export_table", lambda client: None)
    monkeypatch.setattr(cost_module, "_billing_account_diagnostics", lambda project: {"probed": True})

    class _DummyBQ:
        def Client(self, project):
            return object()

    monkeypatch.setattr("google.cloud.bigquery.Client", lambda project: object())
    result = cost_module.run_cost_measurement("proj", days=30)
    assert result["blocked"] is True
    assert "billing export table" in result["reason"]
    assert result["billing_api_diagnostics"] == {"probed": True}


def test_run_cost_measurement_blocked_when_zero_plays(monkeypatch):
    monkeypatch.setattr("google.cloud.bigquery.Client", lambda project: object())
    monkeypatch.setattr(cost_module, "find_billing_export_table", lambda client: "proj.billing.gcp_billing_export_v1_x")
    monkeypatch.setattr(cost_module, "query_genai_cost_inr", lambda client, table, start, end: 42.5)
    monkeypatch.setattr(cost_module, "count_plays_and_avg_rupees", lambda client, ds, start, end: {"plays_in_window": 0, "gaps_in_window": 3, "avg_rupees_at_stake": 9000.0})

    result = cost_module.run_cost_measurement("proj", days=30)
    assert result["blocked"] is True
    assert "0 rows" in result["reason"]
    assert result["genai_cost_inr"] == 42.5


def test_run_cost_measurement_computes_real_numbers_when_data_exists(monkeypatch):
    monkeypatch.setattr("google.cloud.bigquery.Client", lambda project: object())
    monkeypatch.setattr(cost_module, "find_billing_export_table", lambda client: "proj.billing.gcp_billing_export_v1_x")
    monkeypatch.setattr(cost_module, "query_genai_cost_inr", lambda client, table, start, end: 150.0)
    monkeypatch.setattr(cost_module, "count_plays_and_avg_rupees", lambda client, ds, start, end: {"plays_in_window": 30, "gaps_in_window": 40, "avg_rupees_at_stake": 9200.0})

    result = cost_module.run_cost_measurement("proj", days=30)
    assert result["blocked"] is False
    assert result["cost_per_play_inr"] == pytest.approx(5.0)
    assert result["cost_as_pct_of_rupees_at_stake"] == pytest.approx(5.0 / 9200.0, abs=1e-6)


def test_main_exits_nonzero_when_blocked(monkeypatch, capsys):
    monkeypatch.setattr(cost_module, "run_cost_measurement", lambda project, days, dataset: {"blocked": True, "reason": "no export"})
    rc = cost_module.main(["--project", "proj"])
    assert rc == 1
    out = capsys.readouterr().out
    assert "no export" in out
