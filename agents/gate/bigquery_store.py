"""BigQuery-backed system of record for gaps/plays/play_assignments/forecasts/play_outcomes
(DECISIONS §3.3), behind the exact same interface as `LocalStore` (read/write/append/upsert/find).

Item 3 of the "make the architecture true" review: BigQuery becomes the system of record for
these five tables; `LocalStore`/`OverlayStore` stay the per-visitor judge-mode sandbox layer
(§5.6 -- a sandbox genuinely should not hit the warehouse). This class implements exactly that
split for the FIVE named tables: every other table (`products`, `customers`, `consent`, etc.)
falls straight through to `LocalStore`'s file-based behaviour unchanged, table by table, per the
review's own sequencing rule.

Deliberately NOT wired into `services/api/sandbox.py::store_for()` in this session: doing so
changes what the live, judged Cloud Run URL reads and writes on every request, and that redeploy
was not done without a live-verified `make live-test` pass and the user's explicit go-ahead
first (see eval/evaluation.md). `tests/unit/test_bigquery_store.py` covers this module's own
logic (SQL/parameter construction, cache invalidation, non-target-table passthrough) with a fake
client -- this repo's unit tests never touch real GCP credentials or network (see
`tests/unit/test_measure_cost.py`'s own header for the same convention). The real read/write/
append/upsert round trip against the live `amru-509214` project was verified separately with a
throwaway script, not committed as a test; raw evidence: `eval/raw/bigquery_store_2026-09-24/`.

Performance note, why an in-instance cache exists: `LocalStore.read(table)` is called many times
per single Planner run or Customer Agent turn (every tool call re-reads `gaps`/`play_assignments`
freely, since a local JSONL read is nearly free). A BigQuery-backed `read()` doing a fresh
`SELECT *` on every one of those calls would add real network latency and real query cost to
every single tool call inside one already-slow live-Gemini turn. Each `BigQueryStore` instance
therefore caches a table's full row set in memory after its first `read()`/`find()` within that
instance's lifetime (one instance = one API request, per `services/api/sandbox.py::store_for`'s
dependency-injection pattern), and invalidates that table's cache entry on any `write()`/
`append()`/`upsert()` to it. Cross-request staleness (a write from request A not yet visible to a
concurrently-in-flight request B's already-cached read) is the same eventual-consistency window
BigQuery itself has for a fresh SELECT after a streaming insert, not something this cache adds on
top -- see `append()`'s docstring below.
"""
from __future__ import annotations

import os
from collections.abc import Iterable
from typing import Any

from .store import LocalStore

BIGQUERY_TABLES = frozenset({"gaps", "plays", "play_assignments", "forecasts", "play_outcomes"})

# BigQuery has no schema-driven notion of "the row's own id field" the way a JSONL file doesn't
# either; MERGE needs an explicit key list per table. Only `plays` is ever upserted in this
# codebase (grepped every `.upsert(` call site) -- documented here so a future second upsert
# target fails loudly instead of silently matching on the wrong key.
_UPSERT_KEYS: dict[str, tuple[str, ...]] = {
    "plays": ("tenant_id", "play_id"),
}


class BigQueryStore(LocalStore):
    """Drop-in replacement for `LocalStore` on the five named tables; every other table is
    untouched `LocalStore` behaviour (inherited, not reimplemented).
    """

    def __init__(self, root: str | None = None, project: str | None = None, dataset: str = "taal", tenant_id: str = "kutumb-mart"):
        super().__init__(root)
        self.project = project or os.environ.get("GOOGLE_CLOUD_PROJECT", "amru-509214")
        self.dataset = dataset
        self.tenant_id = tenant_id
        self._client = None
        self._cache: dict[str, list[dict[str, Any]]] = {}

    @property
    def client(self):
        if self._client is None:
            from google.cloud import bigquery

            self._client = bigquery.Client(project=self.project)
        return self._client

    def _table(self, table: str) -> str:
        return f"{self.project}.{self.dataset}.{table}"

    def _invalidate(self, table: str) -> None:
        self._cache.pop(table, None)

    def read(self, table: str) -> list[dict[str, Any]]:
        if table not in BIGQUERY_TABLES:
            return super().read(table)
        if table in self._cache:
            return self._cache[table]
        from google.cloud import bigquery

        q = f"SELECT * FROM `{self._table(table)}` WHERE tenant_id = @tenant_id"
        job_config = bigquery.QueryJobConfig(query_parameters=[bigquery.ScalarQueryParameter("tenant_id", "STRING", self.tenant_id)])
        rows = [dict(r) for r in self.client.query(q, job_config=job_config).result()]
        for r in rows:
            for k, v in list(r.items()):
                if hasattr(v, "isoformat"):
                    r[k] = v.isoformat()
        self._cache[table] = rows
        return rows

    def find(self, table: str, **eq: Any) -> list[dict[str, Any]]:
        if table not in BIGQUERY_TABLES:
            return super().find(table, **eq)
        return [r for r in self.read(table) if all(r.get(k) == v for k, v in eq.items())]

    def write(self, table: str, rows: Iterable[dict[str, Any]]) -> None:
        """Full-table replace, matching LocalStore's own semantics (Sense already does a full
        nightly rewrite of `forecasts`/`gaps`; `write()` on this store is that same operation,
        scoped to this tenant only -- WRITE_TRUNCATE would erase every other tenant's rows, so
        this deletes only this tenant's existing rows first, then loads the new set)."""
        if table not in BIGQUERY_TABLES:
            return super().write(table, rows)
        rows = list(rows)
        from google.cloud import bigquery

        self.client.query(
            f"DELETE FROM `{self._table(table)}` WHERE tenant_id = @tenant_id",
            job_config=bigquery.QueryJobConfig(query_parameters=[bigquery.ScalarQueryParameter("tenant_id", "STRING", self.tenant_id)]),
        ).result()
        if rows:
            job_config = bigquery.LoadJobConfig(source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON, write_disposition=bigquery.WriteDisposition.WRITE_APPEND)
            self.client.load_table_from_json(rows, self._table(table), job_config=job_config).result()
        self._invalidate(table)

    def append(self, table: str, rows: Iterable[dict[str, Any]]) -> None:
        """A streaming insert (`insert_rows_json`) lands in seconds, not the minutes a load job
        can take, which matters here: `append()`'s real callers are request-time paths
        (services/api/approve.py writing `play_assignments` inside a live `/approve` call) that
        a judge is actively waiting on. BigQuery's own documented tradeoff applies: a streaming
        buffer's rows can take up to ~90 minutes to become visible to some read APIs, though a
        plain `SELECT` (what `read()` above issues) sees them immediately in practice for a
        small, low-QPS demo tenant like this one -- not a guarantee for a high-volume table."""
        if table not in BIGQUERY_TABLES:
            return super().append(table, rows)
        rows = list(rows)
        if not rows:
            return
        errors = self.client.insert_rows_json(self._table(table), rows)
        if errors:
            raise RuntimeError(f"BigQuery streaming insert into {table} failed: {errors}")
        self._invalidate(table)

    def _schema_types(self, table: str) -> dict[str, str]:
        """The real column types from BigQuery itself, not guessed from the Python value --
        a Python list is genuinely ambiguous between ARRAY<STRING> and JSON (found by running
        this: BigQuery rejected a JSON param for `plays.target_node_ids`, a real ARRAY<STRING>
        column, with 'Value of type JSON cannot be assigned to target_node_ids'). Cached on the
        instance since a table's schema does not change within one request's lifetime."""
        cache_key = f"__schema__{table}"
        if cache_key not in self._cache:
            fields = self.client.get_table(self._table(table)).schema
            self._cache[cache_key] = {f.name: (f.field_type, f.mode) for f in fields}
        return self._cache[cache_key]

    def upsert(self, table: str, key: str, row: dict[str, Any]) -> None:
        if table not in BIGQUERY_TABLES:
            return super().upsert(table, key, row)
        if table not in _UPSERT_KEYS:
            raise NotImplementedError(f"BigQueryStore.upsert has no MERGE key list for {table!r} -- add one to _UPSERT_KEYS rather than guessing")
        from google.cloud import bigquery

        keys = _UPSERT_KEYS[table]
        row = dict(row, tenant_id=self.tenant_id)
        cols = list(row.keys())
        schema = self._schema_types(table)
        on_clause = " AND ".join(f"T.{k} = S.{k}" for k in keys)
        set_clause = ", ".join(f"{c} = S.{c}" for c in cols if c not in keys)
        insert_cols = ", ".join(cols)
        insert_vals = ", ".join(f"S.{c}" for c in cols)
        struct_fields = ", ".join(f"@{c} AS {c}" for c in cols)
        sql = f"""
        MERGE `{self._table(table)}` T
        USING (SELECT {struct_fields}) S
        ON {on_clause}
        WHEN MATCHED THEN UPDATE SET {set_clause}
        WHEN NOT MATCHED THEN INSERT ({insert_cols}) VALUES ({insert_vals})
        """
        import json as _json

        params = []
        for c, v in row.items():
            field_type, mode = schema.get(c, ("STRING", "NULLABLE"))
            if mode == "REPEATED":
                params.append(bigquery.ArrayQueryParameter(c, field_type, v or []))
            elif field_type == "JSON":
                params.append(bigquery.ScalarQueryParameter(c, "JSON", _json.dumps(v, default=str)))
            elif field_type == "BOOL":
                params.append(bigquery.ScalarQueryParameter(c, "BOOL", v))
            else:
                params.append(bigquery.ScalarQueryParameter(c, field_type, v))
        self.client.query(sql, job_config=bigquery.QueryJobConfig(query_parameters=params)).result()
        self._invalidate(table)
