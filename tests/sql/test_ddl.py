import re

import duckdb

from data.bigquery.local import DDL_DIR, table_name, translate_ddl

SMALL = {"products", "nodes", "customers", "affinity", "segments", "estimator_priors", "festival_calendar", "substitutes", "apparel_products"}


def test_every_ddl_applies_on_duckdb():
    con = duckdb.connect()
    for f in sorted(DDL_DIR.glob("*.sql")):
        con.execute(translate_ddl(f.read_text()))
    tables = {r[0] for r in con.execute("select table_name from information_schema.tables").fetchall()}
    for t in ("products", "inventory_batches", "sales_daily", "future_regressors", "gaps", "plays", "play_assignments", "play_outcomes", "consent", "forecasts", "estimator_priors", "execution_events"):
        assert t in tables


def test_every_fact_table_has_partition_or_cluster():
    for f in sorted(DDL_DIR.glob("*.sql")):
        ddl = f.read_text()
        name = table_name(ddl)
        if name in SMALL:
            assert re.search(r"CLUSTER BY", ddl), name
        else:
            assert re.search(r"PARTITION BY", ddl) and re.search(r"CLUSTER BY", ddl), name


def test_every_table_has_tenant_id():
    for f in sorted(DDL_DIR.glob("*.sql")):
        assert "tenant_id STRING NOT NULL" in f.read_text(), f.name
