"""UCI "Online Retail II" -> Taal's store shape (sales_daily, products, nodes).

    python -m data.external.online_retail_ii.load build  --xlsx online_retail_II.xlsx --out data/external/online_retail_ii/sample
    python -m data.external.online_retail_ii.load store  --sample data/external/online_retail_ii/sample --out .local/data-uci

`build` reads the raw workbook (stdlib only: zip + streaming XML, no new dependency), keeps the
top N SKUs by units and writes a small derived sample. `store` turns that sample into the
LocalStore tables jobs/sense reads. The raw workbook is never committed (DATA_LICENSES.md).

Mapping: sku = StockCode; node_id = Country; one cluster ("all"), so the forecaster sees one
series per SKU (the sum over countries). A row of sales_daily is one (date, sku, country) with
units > 0, the same convention data/generator uses (a day with no sale has no row).
Kept lines: Price > 0 and StockCode of the form 12345 / 12345A (drops postage, manual, bank-charge
and fee codes). Sales are Quantity > 0 lines; cancellation lines (invoice "C...") are netted off
within the same (date, sku, country) and the cell is floored at 0, so an order reversed the same
day (e.g. the 80,995-unit line of 2011-12-09) does not count as demand. Later returns are not netted.

Absent in this dataset and left None, never invented: category, unit_cost, shelf_life_days,
is_food, expiry, on-hand stock, inbound orders, lead time, promo flags (on_promo is False = unknown).
"""
from __future__ import annotations

import argparse
import gzip
import io
import json
import re
import sys
import zipfile
from collections import Counter, defaultdict
from collections.abc import Iterator
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from xml.etree.ElementTree import iterparse

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
TENANT = "online_retail_ii"
CLUSTER = "all"
STOCK_CODE = re.compile(r"^\d{5}[A-Za-z]{0,2}$")
ABSENT = ["category", "unit_cost", "shelf_life_days", "is_food", "expiry_date", "qty_on_hand", "inbound", "lead_time_days", "on_promo"]


def serial_to_date(serial: float) -> date:
    return (datetime(1899, 12, 30) + timedelta(days=int(serial))).date()


def keep_line(invoice: str, stock: str, qty: float, price: float) -> bool:
    """A sale line (qty > 0) or a cancellation line (invoice "C...", qty < 0) of a real product code."""
    return price > 0 and bool(STOCK_CODE.match(stock)) and (qty > 0) != invoice.upper().startswith("C") and qty != 0


def _sheets(xlsx: Path) -> Iterator[tuple[str, list[str], Iterator[list[Any]]]]:
    zf = zipfile.ZipFile(xlsx)
    shared = [("".join(t.text or "" for t in si.iter(f"{NS}t"))) for _, si in iterparse(io.BytesIO(zf.read("xl/sharedStrings.xml"))) if si.tag == f"{NS}si"]
    for name in sorted(n for n in zf.namelist() if n.startswith("xl/worksheets/sheet")):
        yield name, shared, _rows(zf.open(name), shared)


def _rows(fh, shared: list[str]) -> Iterator[list[Any]]:
    for _, el in iterparse(fh):
        if el.tag != f"{NS}row":
            continue
        row: list[Any] = [None] * 8
        for c in el.iter(f"{NS}c"):
            col = ord(c.get("r")[0]) - 65
            v = c.find(f"{NS}v")
            if v is None or col > 7:
                continue
            row[col] = shared[int(v.text)] if c.get("t") == "s" else (v.text if c.get("t") in ("str", "inlineStr") else float(v.text))
        el.clear()
        yield row


def build(xlsx: Path, out: Path, top: int) -> dict[str, Any]:
    """Raw workbook -> sample dir (sales_daily.jsonl.gz, products.jsonl, nodes.jsonl, meta.json)."""
    daily: dict[tuple[date, str, str], list[float]] = defaultdict(lambda: [0.0, 0.0])
    names: dict[str, Counter] = defaultdict(Counter)
    seen = kept = 0
    for _, _, rows in _sheets(xlsx):
        for r in rows:
            if r[0] in (None, "Invoice") or not isinstance(r[4], float):
                continue
            seen += 1
            invoice, stock, desc, qty, serial, price, _cust, country = str(r[0]), str(r[1]), r[2], r[3] or 0.0, r[4], r[5] or 0.0, r[6], r[7]
            if stock.endswith(".0"):
                stock = stock[:-2]
            if not keep_line(invoice, stock, qty, price):
                continue
            kept += 1
            cell = daily[(serial_to_date(serial), stock, country)]
            cell[0] += qty
            cell[1] += qty * price
            if desc and qty > 0:
                names[stock][desc.strip()] += 1
    daily = {k: v for k, v in daily.items() if v[0] >= 1}  # cancellations netted; fully reversed cells vanish
    units = Counter()
    for (_, sku, _), (q, _) in daily.items():
        units[sku] += q
    top_skus = {s for s, _ in units.most_common(top)}
    out.mkdir(parents=True, exist_ok=True)
    rows = sorted((d, s, n, q, rev) for (d, s, n), (q, rev) in daily.items() if s in top_skus)
    with gzip.GzipFile(out / "sales_daily.jsonl.gz", "wb", 9, mtime=0) as gz, io.TextIOWrapper(gz, encoding="utf-8", newline="\n") as f:  # mtime=0: byte-stable
        for d, s, n, q, rev in rows:
            f.write(json.dumps({"date": d.isoformat(), "sku": s, "node_id": n, "units": int(q), "revenue": round(rev, 2)}, separators=(",", ":")) + "\n")
    price_sum = defaultdict(float)
    for _, s, _, _, rev in rows:
        price_sum[s] += rev
    with open(out / "products.jsonl", "w", encoding="utf-8") as f:
        for s in sorted(top_skus):
            f.write(json.dumps({"sku": s, "name": names[s].most_common(1)[0][0], "list_price_gbp": round(price_sum[s] / units[s], 2), "units_total": int(units[s])}) + "\n")
    countries = sorted({n for _, _, n, _, _ in rows})
    meta = {"source_rows": seen, "kept_lines": kept, "top_skus": len(top_skus), "sales_rows": len(rows), "countries": len(countries),
            "first_date": rows[0][0].isoformat(), "last_date": max(r[0] for r in rows).isoformat(), "absent_fields": ABSENT}
    (out / "meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    return meta


def sample_to_tables(sample: Path) -> dict[str, list[dict[str, Any]]]:
    """Sample dir -> the LocalStore tables the forecaster and backtest read. Fields the dataset lacks are None."""
    with gzip.open(sample / "sales_daily.jsonl.gz", "rt", encoding="utf-8") as f:
        sales = [{"tenant_id": TENANT, **json.loads(line), "on_promo": False} for line in f]
    products = [{"tenant_id": TENANT, "sku": p["sku"], "name": p["name"], "category": "unclassified", "pack_size": None, "pack_weight_g": None,
                 "unit_cost": None, "list_price": p["list_price_gbp"], "margin_floor_pct": None, "shelf_life_days": None, "is_food": None}
                for p in (json.loads(line) for line in open(sample / "products.jsonl", encoding="utf-8"))]
    nodes = [{"tenant_id": TENANT, "node_id": c, "name": c, "type": "dark_store", "lat": None, "lng": None, "lead_time_days": None, "cluster_id": CLUSTER}
             for c in sorted({s["node_id"] for s in sales})]
    return {"sales_daily": sales, "products": products, "nodes": nodes, "inventory_batches": [], "inbound": [], "future_regressors": []}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--xlsx", required=True, type=Path)
    b.add_argument("--out", required=True, type=Path)
    b.add_argument("--top", type=int, default=300)
    s = sub.add_parser("store")
    s.add_argument("--sample", required=True, type=Path)
    s.add_argument("--out", required=True, type=Path)
    a = ap.parse_args(argv)
    if a.cmd == "build":
        print(json.dumps(build(a.xlsx, a.out, a.top), indent=2))
    else:
        from agents.gate.store import LocalStore

        store = LocalStore(a.out)
        for t, rows in sample_to_tables(a.sample).items():
            store.write(t, rows)
        print(f"wrote {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
