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
    monkeypatch.setattr(cost_module, "run_modeled_cost_measurement", lambda project, days, dataset: {"methodology": "modeled_from_measured_usage", "total_inr": 12.3, "lines": {}, "unavailable_lines": []})

    monkeypatch.setattr("google.cloud.bigquery.Client", lambda project: object())
    result = cost_module.run_cost_measurement("proj", days=30)
    assert result["blocked"] is True
    assert "billing export table" in result["reason"]
    assert result["billing_api_diagnostics"] == {"probed": True}
    assert result["modeled"]["total_inr"] == 12.3


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


def test_main_exits_zero_when_tier1_blocked_but_tier2_modeled(monkeypatch, capsys):
    modeled = {"lines": {"vertex_ai_gemini": {"usd": 1.0}}, "unavailable_lines": []}
    monkeypatch.setattr(cost_module, "run_cost_measurement", lambda project, days, dataset: {"blocked": True, "reason": "no export", "modeled": modeled})
    rc = cost_module.main(["--project", "proj"])
    assert rc == 0


def test_main_exits_nonzero_when_both_tiers_empty(monkeypatch):
    modeled = {"lines": {"vertex_ai_gemini": {}}, "unavailable_lines": ["vertex_ai_gemini"]}
    monkeypatch.setattr(cost_module, "run_cost_measurement", lambda project, days, dataset: {"blocked": True, "reason": "no export", "modeled": modeled})
    rc = cost_module.main(["--project", "proj"])
    assert rc == 1


class _FakePoint:
    def __init__(self, value):
        self.value = value


class _FakeValue:
    def __init__(self, v):
        self.int64_value = v
        self.double_value = 0


class _FakeTimeSeries:
    def __init__(self, metric_labels, resource_labels, values):
        self.metric = type("M", (), {"labels": metric_labels})()
        self.resource = type("R", (), {"labels": resource_labels})()
        self.points = [type("P", (), {"value": _FakeValue(v)})() for v in values]


def test_sum_delta_metric_sums_real_series(monkeypatch):
    class _FakeMonClient:
        def list_time_series(self, request):
            return [_FakeTimeSeries({"type": "input"}, {"source": "asia-south1"}, [10, 20, 30])]

    total = cost_module._sum_delta_metric(_FakeMonClient(), "proj", "some.metric/type", cost_module.datetime.now(cost_module.UTC), cost_module.datetime.now(cost_module.UTC))
    assert total["available"] is True
    assert total["total"] == 60
    assert total["n_series"] == 1


def test_sum_delta_metric_reports_error_not_zero(monkeypatch):
    class _FailingMonClient:
        def list_time_series(self, request):
            raise RuntimeError("permission denied")

    result = cost_module._sum_delta_metric(_FailingMonClient(), "proj", "some.metric/type", cost_module.datetime.now(cost_module.UTC), cost_module.datetime.now(cost_module.UTC))
    assert result["available"] is False
    assert "permission denied" in result["error"]


def test_run_modeled_cost_measurement_prices_real_measured_usage(monkeypatch):
    def fake_sum(mon_client, project, metric_type, start, end, metric_filter=""):
        if "token_count" in metric_type and 'type"="input"' in metric_filter:
            return {"available": True, "total": 1_000_000.0, "n_series": 1, "series": []}
        if "token_count" in metric_type and 'type"="output"' in metric_filter:
            return {"available": True, "total": 500_000.0, "n_series": 1, "series": []}
        if "cpu/allocation_time" in metric_type:
            return {"available": True, "total": 100.0, "n_series": 1, "series": []}
        if "memory/allocation_time" in metric_type:
            return {"available": True, "total": 50.0, "n_series": 1, "series": []}
        if "read_units" in metric_type:
            return {"available": True, "total": 0.0, "n_series": 0, "series": []}
        if "write_units" in metric_type:
            return {"available": True, "total": 0.0, "n_series": 0, "series": []}
        return {"available": False, "error": "unused metric in this test"}

    monkeypatch.setattr(cost_module, "_sum_delta_metric", fake_sum)
    monkeypatch.setattr("google.cloud.monitoring_v3.MetricServiceClient", lambda: object())

    class _FakeJob:
        total_bytes_billed = 10_485_760  # 10 MiB, BigQuery's real minimum-billed floor

    class _FakeBQClient:
        project = "proj"

        def list_jobs(self, **kwargs):
            return [_FakeJob()]

        def list_datasets(self):
            return []

    monkeypatch.setattr("google.cloud.bigquery.Client", lambda project: _FakeBQClient())
    monkeypatch.setattr(cost_module, "count_plays_and_avg_rupees", lambda client, ds, start, end: {"plays_in_window": 10, "gaps_in_window": 5, "avg_rupees_at_stake": 9200.0})

    result = cost_module.run_modeled_cost_measurement("proj", days=30, dataset="taal")
    assert result["methodology"] == "modeled_from_measured_usage"
    # 1M input @ $0.30/M + 0.5M output @ $2.50/M = 0.30 + 1.25 = 1.55 USD from Gemini alone
    assert result["lines"]["vertex_ai_gemini"]["usd"] == pytest.approx(1.55, abs=1e-6)
    assert result["lines"]["firestore"]["usd"] == 0.0
    assert result["unavailable_lines"] == []
    assert result["cost_per_play_inr"] is not None
    assert result["total_usd"] > 0
