"""DuckDB stand-in for the BigQuery dataset so DDL and assertions run in CI without cloud.

Translation is deliberately small (DECISIONS step 19): strip backticks and the dataset prefix,
drop PARTITION BY / CLUSTER BY, map BigQuery types to DuckDB types (STRUCT<...> -> STRUCT(...),
ARRAY<T> -> T[], INT64 -> BIGINT, FLOAT64 -> DOUBLE, BOOL -> BOOLEAN, JSON -> JSON). Tables are
loaded from the JSONL store by name. Assertion files return violating rows; zero rows = pass.
"""
from __future__ import annotations

import re
from pathlib import Path

import duckdb

from agents.gate.config import ROOT
from agents.gate.store import LocalStore

DDL_DIR = ROOT / "data" / "bigquery" / "ddl"
ASSERTIONS_DIR = ROOT / "data" / "bigquery" / "assertions"


def translate_ddl(sql: str) -> str:
    sql = re.sub(r"--[^\n]*", "", sql)
    sql = sql.replace("`", "")
    sql = re.sub(r"\btaal\.", "", sql)
    sql = re.sub(r"\bPARTITION BY\s+[^\n;]+", "", sql)
    sql = re.sub(r"\bCLUSTER BY\s+[^\n;]+", "", sql)
    # nested generics: ARRAY<STRING> -> STRING[], STRUCT<a T, b U> -> STRUCT(a T, b U)
    while re.search(r"ARRAY<[^<>]+>", sql):
        sql = re.sub(r"ARRAY<([^<>]+)>", r"\1[]", sql)
    while re.search(r"STRUCT<[^<>]+>", sql):
        sql = re.sub(r"STRUCT<([^<>]+)>", r"STRUCT(\1)", sql)
    sql = re.sub(r"\bINT64\b", "BIGINT", sql)
    sql = re.sub(r"\bFLOAT64\b", "DOUBLE", sql)
    sql = re.sub(r"\bBOOL\b", "BOOLEAN", sql)
    sql = re.sub(r"\bSTRING\b", "VARCHAR", sql)
    sql = re.sub(r"\s+NOT NULL", "", sql)
    return sql.strip()


def table_name(ddl: str) -> str:
    m = re.search(r"CREATE TABLE IF NOT EXISTS\s+`?taal\.(\w+)`?", ddl)
    if not m:
        raise ValueError("no CREATE TABLE in DDL")
    return m.group(1)


def apply_ddl(con: duckdb.DuckDBPyConnection) -> list[str]:
    names = []
    for f in sorted(DDL_DIR.glob("*.sql")):
        ddl = f.read_text(encoding="utf-8")
        con.execute(translate_ddl(ddl))
        names.append(table_name(ddl))
    return names


def load_store(con: duckdb.DuckDBPyConnection, store: LocalStore, tables: list[str] | None = None) -> dict[str, int]:
    counts = {}
    known = {r[0] for r in con.execute("SELECT table_name FROM information_schema.tables").fetchall()}
    for name in tables or sorted(known):
        if name not in known:
            continue
        path = store._path(name) if hasattr(store, "_path") else store.root / f"{name}.jsonl"
        if not Path(path).exists() or Path(path).stat().st_size == 0:
            counts[name] = 0
            continue
        cols = [r[0] for r in con.execute(f"SELECT column_name FROM information_schema.columns WHERE table_name = '{name}' ORDER BY ordinal_position").fetchall()]
        src_cols = {r[0] for r in con.execute(f"DESCRIBE SELECT * FROM read_json_auto('{path}', format='newline_delimited', union_by_name=true, maximum_object_size=4000000)").fetchall()}
        use = [c for c in cols if c in src_cols]
        col_list = ", ".join(f'"{c}"' for c in use)
        con.execute(f"INSERT INTO {name} ({col_list}) SELECT {col_list} FROM read_json_auto('{path}', format='newline_delimited', union_by_name=true, maximum_object_size=4000000)")
        counts[name] = con.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
    return counts


def build(store: LocalStore, path: str | None = None) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(path or ":memory:")
    apply_ddl(con)
    load_store(con, store)
    return con


def run_assertion(con: duckdb.DuckDBPyConnection, sql_file: Path) -> list[tuple]:
    sql = sql_file.read_text(encoding="utf-8")
    return con.execute(sql).fetchall()


def run_all_assertions(con: duckdb.DuckDBPyConnection) -> dict[str, list[tuple]]:
    return {f.name: run_assertion(con, f) for f in sorted(ASSERTIONS_DIR.glob("*.sql"))}
