"""LocalStore tenant -> the contract CSVs (the inverse of data.ingest), for the round-trip proof and
the committed samples.

    python -m data.ingest.export --data .local/data --out .local/export [--sample]

Writes products.csv, inventory_batches.csv, sales.csv, nodes.csv, inbound.csv with exactly the
contract columns (data/ingest/contract.py): no tenant_id, no derived online_sellby_date, no node
display names. Floats are written with repr(), so reading them back gives the same float.

--sample writes a small, self-consistent slice for data/samples/ instead of the whole tenant:
the planted Masala Chips lot at DS-07 (six days from its online sell-by) and the Darjeeling tea
lot at DS-04, with the sales history of just those (sku, node) pairs -- at most 200 rows a file.
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Any

from agents.gate.store import LocalStore

from .contract import CONTRACT

FILES = {"products": "products.csv", "inventory_batches": "inventory_batches.csv", "sales_daily": "sales.csv", "nodes": "nodes.csv", "inbound": "inbound.csv"}
CONTRACT_KEY = {"products": "products", "inventory_batches": "inventory_batches", "sales_daily": "sales", "nodes": "nodes", "inbound": "inbound"}
SAMPLE_PAIRS = {("SKU-MASALA-CHIPS-200G", "DS-07"), ("SKU-DARJEELING-TEA-100G", "DS-04")}
SAMPLE_MAX_ROWS = 200


def _cell(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float):
        return repr(v)
    return str(v)


def _write(path: Path, columns: list[str], rows: list[dict[str, Any]]) -> None:
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(columns)
        for r in rows:
            w.writerow([_cell(r.get(c)) for c in columns])


def export(data: str | Path, out: str | Path, sample: bool = False) -> dict[str, int]:
    store = LocalStore(data)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    tables = {t: store.read(t) for t in FILES}
    if sample:
        skus = {s for s, _ in SAMPLE_PAIRS}
        nodes = {n for _, n in SAMPLE_PAIRS}
        tables["products"] = [p for p in tables["products"] if p["sku"] in skus]
        tables["nodes"] = [n for n in tables["nodes"] if n["node_id"] in nodes]
        for t in ("inventory_batches", "sales_daily", "inbound"):
            tables[t] = [r for r in tables[t] if (r["sku"], r["node_id"]) in SAMPLE_PAIRS]
        for t, rows in tables.items():
            if len(rows) > SAMPLE_MAX_ROWS:
                raise ValueError(f"sample {t} has {len(rows)} rows, over the {SAMPLE_MAX_ROWS}-row cap")
    counts = {}
    for t, fname in FILES.items():
        if sample and not tables[t]:
            continue
        columns = [c.name for c in CONTRACT[CONTRACT_KEY[t]]]
        _write(out / fname, columns, tables[t])
        counts[fname] = len(tables[t])
    return counts


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m data.ingest.export", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default=".local/data")
    ap.add_argument("--out", required=True)
    ap.add_argument("--sample", action="store_true")
    args = ap.parse_args(argv)
    for fname, n in export(args.data, args.out, args.sample).items():
        print(f"{Path(args.out) / fname}: {n} rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
