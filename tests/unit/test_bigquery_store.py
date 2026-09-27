"""agents.gate.bigquery_store: pure-logic tests against a fake BigQuery client -- this repo's
unit tests never touch real GCP credentials or network (see test_measure_cost.py's own header
for the same convention). The real round trip against amru-509214 was verified separately with a
throwaway script; raw evidence: eval/raw/bigquery_store_2026-09-24/.
"""
from __future__ import annotations

import pytest
from google.cloud import bigquery

from agents.gate.bigquery_store import BigQueryStore

# write() now passes a fetched schema straight into a real bigquery.LoadJobConfig(schema=...),
# which validates its contents -- a plain shim object no longer satisfies it, so tests use the
# real SchemaField class directly instead of a custom fake.
_FakeField = bigquery.SchemaField


class _FakeTable:
    def __init__(self, schema):
        self.schema = schema


class _FakeJob:
    def __init__(self, rows=None):
        self._rows = rows or []

    def result(self):
        return self._rows


class _FakeClient:
    def __init__(self, query_rows=None, schema=None, insert_errors=None, fail_load=False, fail_script=False):
        self.query_rows = query_rows or []
        self.schema = schema or []
        self.insert_errors = insert_errors if insert_errors is not None else []
        self.fail_load = fail_load
        self.fail_script = fail_script
        self.queries: list[str] = []
        self.query_params: list[list] = []
        self.loaded_rows: list[list[dict]] = []
        self.loaded_tables: list[str] = []
        self.load_job_configs: list = []
        self.inserted_rows: list[list[dict]] = []
        self.dropped_tables: list[str] = []

    def query(self, sql, job_config=None):
        if self.fail_script and "BEGIN TRANSACTION" in sql:
            raise RuntimeError("simulated script failure")
        self.queries.append(sql)
        self.query_params.append(list(job_config.query_parameters) if job_config and job_config.query_parameters else [])
        return _FakeJob(self.query_rows)

    def get_table(self, table_ref):
        return _FakeTable(self.schema)

    def load_table_from_json(self, rows, table_ref, job_config=None):
        if self.fail_load:
            raise RuntimeError("simulated load failure")
        self.loaded_rows.append(list(rows))
        self.loaded_tables.append(table_ref)
        self.load_job_configs.append(job_config)
        return _FakeJob()

    def insert_rows_json(self, table_ref, rows):
        self.inserted_rows.append(list(rows))
        return self.insert_errors

    def delete_table(self, table_ref, not_found_ok=True):
        self.dropped_tables.append(table_ref)


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
    # 1 (initial read) + 2 (write()'s own CREATE TABLE + staged transaction script) + 1 (this
    # second read, proving the cache was invalidated rather than serving the stale first result)
    assert len(client.queries) == 4, "write() must invalidate the cache so the next read() hits BigQuery again"


def test_append_invalidates_cache(tmp_path):
    client = _FakeClient(query_rows=[{"play_id": "p1"}])
    s = _store(tmp_path, client)
    s.read("play_assignments")
    s.append("play_assignments", [{"play_id": "p1", "customer_id": "c1", "tenant_id": "kutumb-mart"}])
    client.query_rows = [{"play_id": "p1"}, {"play_id": "p1", "customer_id": "c1"}]
    s.read("play_assignments")
    assert len(client.queries) == 2


def test_write_stages_then_deletes_this_tenant_and_inserts_via_transaction(tmp_path):
    client = _FakeClient()
    s = _store(tmp_path, client)
    s.write("gaps", [{"gap_id": "g1", "tenant_id": "kutumb-mart"}])
    # first, an empty staging table is created LIKE the real one (no explicit Python-side schema,
    # which round-trips nested RECORD columns like gaps.evidence lossily)
    assert len(client.queries) == 2
    assert "CREATE TABLE" in client.queries[0] and "LIKE" in client.queries[0]
    # the new rows are loaded into that staging table, never the real table directly
    assert client.loaded_rows == [[{"gap_id": "g1", "tenant_id": "kutumb-mart"}]]
    assert client.loaded_tables[0] != s._table("gaps") and "gaps_stage_" in client.loaded_tables[0]
    # then exactly one scripted transaction does the delete+insert swap
    assert "BEGIN TRANSACTION" in client.queries[1] and "COMMIT TRANSACTION" in client.queries[1]
    assert "DELETE FROM" in client.queries[1] and "INSERT INTO" in client.queries[1]
    assert client.query_params[1][0].name == "tenant_id" and client.query_params[1][0].value == "kutumb-mart"
    # gaps is not run-scoped: no run_id parameter, tenant-wide delete is the intended nightly replace
    assert [p.name for p in client.query_params[1]] == ["tenant_id"]
    # the staging table is always dropped afterwards, success or failure
    assert client.dropped_tables == [client.loaded_tables[0]]


def test_write_empty_rows_deletes_but_does_not_load(tmp_path):
    client = _FakeClient()
    s = _store(tmp_path, client)
    s.write("gaps", [])
    assert len(client.queries) == 1
    assert "DELETE FROM" in client.queries[0]
    assert client.loaded_rows == []


def test_write_forecasts_scopes_delete_to_run_id_not_tenant_wide(tmp_path):
    client = _FakeClient()
    s = _store(tmp_path, client)
    s.write("forecasts", [{"sku": "S1", "tenant_id": "kutumb-mart", "run_id": "run-A"}])
    assert len(client.queries) == 2  # CREATE TABLE ... LIKE, then the scripted transaction
    assert "DELETE FROM" in client.queries[1] and "run_id" in client.queries[1]
    param_names = {p.name for p in client.query_params[1]}
    assert param_names == {"tenant_id", "run_id"}
    run_id_param = next(p for p in client.query_params[1] if p.name == "run_id")
    assert run_id_param.value == "run-A"


def test_write_forecasts_with_mixed_run_ids_raises_rather_than_guessing_scope(tmp_path):
    client = _FakeClient()
    s = _store(tmp_path, client)
    with pytest.raises(ValueError, match="run_id"):
        s.write("forecasts", [{"sku": "S1", "run_id": "run-A"}, {"sku": "S2", "run_id": "run-B"}])
    # nothing should have been touched before the row-shape check failed
    assert client.queries == [] and client.loaded_rows == []


def test_write_forecasts_empty_rows_is_a_no_op_not_a_tenant_wide_delete(tmp_path):
    client = _FakeClient()
    s = _store(tmp_path, client)
    s.write("forecasts", [])
    assert client.queries == [] and client.loaded_rows == []


def test_write_json_safe_converts_date_and_decimal_before_loading(tmp_path):
    from datetime import date
    from decimal import Decimal
    client = _FakeClient()
    s = _store(tmp_path, client)
    s.write("gaps", [{"gap_id": "g1", "tenant_id": "kutumb-mart", "deadline_date": date(2026, 10, 1), "rupees_at_stake": Decimal("123.45")}])
    loaded = client.loaded_rows[0][0]
    assert loaded["deadline_date"] == "2026-10-01"
    assert loaded["rupees_at_stake"] == 123.45 and isinstance(loaded["rupees_at_stake"], float)


def test_write_json_safe_converts_date_for_forecasts_too(tmp_path):
    from datetime import date
    client = _FakeClient()
    s = _store(tmp_path, client)
    s.write("forecasts", [{"sku": "S1", "tenant_id": "kutumb-mart", "run_id": "run-A", "date": date(2026, 10, 1)}])
    assert client.loaded_rows[0][0]["date"] == "2026-10-01"


def test_write_insert_uses_named_columns_not_positional_star(tmp_path):
    schema = [_FakeField("tenant_id", "STRING"), _FakeField("gap_id", "STRING"), _FakeField("deadline_date", "DATE")]
    client = _FakeClient(schema=schema)
    s = _store(tmp_path, client)
    s.write("gaps", [{"gap_id": "g1", "tenant_id": "kutumb-mart", "deadline_date": "2026-10-01"}])
    script = client.queries[1]
    assert "INSERT INTO" in script and "SELECT" in script
    assert "tenant_id, gap_id, deadline_date" in script, "column list must be explicit and name-matched, never a positional SELECT *"
    assert "SELECT *" not in script


def test_write_load_passes_explicit_schema_not_left_to_inference(tmp_path):
    # Found live (2026-09-27): load_table_from_json with WRITE_TRUNCATE into an EXISTING table,
    # given no explicit schema=, infers a schema from the batch of rows instead of respecting the
    # table's declared one -- silently reordering a nested RECORD's subfields and dropping any
    # subfield absent from every row in the batch. The fix is to always pass the real, unmodified
    # schema fetched from get_table() to the load's own job_config.
    schema = [_FakeField("tenant_id", "STRING"), _FakeField("gap_id", "STRING")]
    client = _FakeClient(schema=schema)
    s = _store(tmp_path, client)
    s.write("gaps", [{"gap_id": "g1", "tenant_id": "kutumb-mart"}])
    assert len(client.load_job_configs) == 1
    assert client.load_job_configs[0].schema == schema


def test_write_load_failure_leaves_existing_rows_untouched(tmp_path):
    client = _FakeClient(fail_load=True)
    s = _store(tmp_path, client)
    with pytest.raises(RuntimeError, match="simulated load failure"):
        s.write("gaps", [{"gap_id": "g1", "tenant_id": "kutumb-mart"}])
    # the load failed before any DELETE/INSERT was ever issued against the real table -- only the
    # (harmless, empty) staging table's own CREATE ran, and it gets cleaned up regardless
    assert len(client.queries) == 1 and "CREATE TABLE" in client.queries[0]
    assert not any("DELETE FROM" in q or "INSERT INTO" in q for q in client.queries)
    assert client.dropped_tables, "the staging table must be dropped even though the load into it failed"


def test_write_transaction_failure_leaves_existing_rows_untouched_and_drops_staging(tmp_path):
    client = _FakeClient(fail_script=True)
    s = _store(tmp_path, client)
    with pytest.raises(RuntimeError, match="simulated script failure"):
        s.write("gaps", [{"gap_id": "g1", "tenant_id": "kutumb-mart"}])
    # the staged rows landed in the staging table (never the real one), the transaction that
    # would have deleted the real table's rows never committed, and the staging table is still
    # cleaned up even though the script failed
    assert client.loaded_rows == [[{"gap_id": "g1", "tenant_id": "kutumb-mart"}]]
    assert client.dropped_tables == client.loaded_tables


def test_append_json_safe_converts_date_before_streaming(tmp_path):
    from datetime import date
    client = _FakeClient()
    s = _store(tmp_path, client)
    s.append("play_assignments", [{"play_id": "p1", "assigned_at": date(2026, 10, 1)}])
    assert client.inserted_rows[0][0]["assigned_at"] == "2026-10-01"


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
