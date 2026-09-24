"""agents.gate.bigquery_store: pure-logic tests against a fake BigQuery client -- this repo's
unit tests never touch real GCP credentials or network (see test_measure_cost.py's own header
for the same convention). The real round trip against amru-509214 was verified separately with a
throwaway script; raw evidence: eval/raw/bigquery_store_2026-09-24/.
"""
from __future__ import annotations

import pytest
from google.cloud import bigquery

from agents.gate.bigquery_store import BigQueryStore


class _FakeField:
    def __init__(self, name, field_type, mode="NULLABLE"):
        self.name = name
        self.field_type = field_type
        self.mode = mode


class _FakeTable:
    def __init__(self, schema):
        self.schema = schema


class _FakeJob:
    def __init__(self, rows=None):
        self._rows = rows or []

    def result(self):
        return self._rows


class _FakeClient:
    def __init__(self, query_rows=None, schema=None, insert_errors=None):
        self.query_rows = query_rows or []
        self.schema = schema or []
        self.insert_errors = insert_errors if insert_errors is not None else []
        self.queries: list[str] = []
        self.query_params: list[list] = []
        self.loaded_rows: list[list[dict]] = []
        self.inserted_rows: list[list[dict]] = []

    def query(self, sql, job_config=None):
        self.queries.append(sql)
        self.query_params.append(list(job_config.query_parameters) if job_config and job_config.query_parameters else [])
        return _FakeJob(self.query_rows)

    def get_table(self, table_ref):
        return _FakeTable(self.schema)

    def load_table_from_json(self, rows, table_ref, job_config=None):
        self.loaded_rows.append(list(rows))
        return _FakeJob()

    def insert_rows_json(self, table_ref, rows):
        self.inserted_rows.append(list(rows))
        return self.insert_errors


def _store(tmp_path, client):
    s = BigQueryStore(root=str(tmp_path), project="proj", tenant_id="kutumb-mart")
    s._client = client
    return s


def test_non_target_table_passthrough_to_localstore(tmp_path):
    client = _FakeClient()
    s = _store(tmp_path, client)
    s.write("products", [{"sku": "S1", "name": "Chips"}])
    assert s.find("products", sku="S1") == [{"sku": "S1", "name": "Chips"}]
    s.append("products", [{"sku": "S2", "name": "Tea"}])
    assert len(s.read("products")) == 2
    # none of this should have touched the fake BigQuery client at all
    assert client.queries == [] and client.loaded_rows == [] and client.inserted_rows == []


def test_read_caches_across_calls_and_find_reuses_cache(tmp_path):
    client = _FakeClient(query_rows=[{"gap_id": "g1", "tenant_id": "kutumb-mart"}])
    s = _store(tmp_path, client)
    assert s.read("gaps") == [{"gap_id": "g1", "tenant_id": "kutumb-mart"}]
    assert s.find("gaps", gap_id="g1") == [{"gap_id": "g1", "tenant_id": "kutumb-mart"}]
    assert s.find("gaps", gap_id="missing") == []
    assert len(client.queries) == 1, "read()+find()x2 on the same table should issue exactly one real query"


def test_write_invalidates_cache_so_next_read_refetches(tmp_path):
    client = _FakeClient(query_rows=[{"gap_id": "g1"}])
    s = _store(tmp_path, client)
    s.read("gaps")
    assert len(client.queries) == 1
    s.write("gaps", [{"gap_id": "g2", "tenant_id": "kutumb-mart"}])
    client.query_rows = [{"gap_id": "g2"}]
    assert s.read("gaps") == [{"gap_id": "g2"}]
    # 1 (initial read) + 1 (write()'s own DELETE) + 1 (this second read, proving the cache was
    # invalidated rather than serving the stale first result) = 3
    assert len(client.queries) == 3, "write() must invalidate the cache so the next read() hits BigQuery again"


def test_append_invalidates_cache(tmp_path):
    client = _FakeClient(query_rows=[{"play_id": "p1"}])
    s = _store(tmp_path, client)
    s.read("play_assignments")
    s.append("play_assignments", [{"play_id": "p1", "customer_id": "c1", "tenant_id": "kutumb-mart"}])
    client.query_rows = [{"play_id": "p1"}, {"play_id": "p1", "customer_id": "c1"}]
    s.read("play_assignments")
    assert len(client.queries) == 2


def test_write_deletes_this_tenant_then_loads_new_rows(tmp_path):
    client = _FakeClient()
    s = _store(tmp_path, client)
    s.write("gaps", [{"gap_id": "g1", "tenant_id": "kutumb-mart"}])
    assert len(client.queries) == 1 and "DELETE FROM" in client.queries[0]
    assert client.query_params[0][0].name == "tenant_id" and client.query_params[0][0].value == "kutumb-mart"
    assert client.loaded_rows == [[{"gap_id": "g1", "tenant_id": "kutumb-mart"}]]


def test_write_empty_rows_deletes_but_does_not_load(tmp_path):
    client = _FakeClient()
    s = _store(tmp_path, client)
    s.write("gaps", [])
    assert len(client.queries) == 1
    assert client.loaded_rows == []


def test_append_raises_on_streaming_insert_errors(tmp_path):
    client = _FakeClient(insert_errors=[{"index": 0, "errors": [{"reason": "invalid"}]}])
    s = _store(tmp_path, client)
    with pytest.raises(RuntimeError, match="streaming insert"):
        s.append("play_assignments", [{"play_id": "p1"}])


def test_upsert_uses_real_schema_for_array_and_json_types(tmp_path):
    schema = [
        _FakeField("tenant_id", "STRING"),
        _FakeField("play_id", "STRING"),
        _FakeField("target_node_ids", "STRING", mode="REPEATED"),
        _FakeField("play_json", "JSON"),
    ]
    client = _FakeClient(schema=schema)
    s = _store(tmp_path, client)
    s.upsert("plays", "play_id", {"play_id": "p1", "target_node_ids": ["DS-01", "DS-02"], "play_json": {"a": 1}})
    assert len(client.queries) == 1 and "MERGE" in client.queries[0]
    params_by_name = {p.name: p for p in client.query_params[0]}
    assert isinstance(params_by_name["target_node_ids"], bigquery.ArrayQueryParameter)
    assert params_by_name["target_node_ids"].array_type == "STRING"
    assert params_by_name["target_node_ids"].values == ["DS-01", "DS-02"]
    assert params_by_name["play_json"].type_ == "JSON"
    assert params_by_name["play_json"].value == '{"a": 1}'


def test_upsert_on_a_table_with_no_registered_merge_key_raises(tmp_path):
    s = _store(tmp_path, _FakeClient())
    with pytest.raises(NotImplementedError, match="gaps"):
        s.upsert("gaps", "gap_id", {"gap_id": "g1"})


def test_upsert_on_non_target_table_falls_through_to_localstore(tmp_path):
    client = _FakeClient()
    s = _store(tmp_path, client)
    s.upsert("offers", "offer_id", {"offer_id": "o1", "text": "hi"})
    assert s.find("offers", offer_id="o1") == [{"offer_id": "o1", "text": "hi"}]
    assert client.queries == []
