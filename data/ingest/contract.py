"""The three-CSV ingestion contract (docs/scale.md, "The three-CSV ingestion contract"), as code.

Each file is a list of `Column`s: a name, a parser that turns the cell text into the value the
LocalStore row carries (the same types data/generator writes), and whether a blank cell is allowed.
Validation collects every problem with its file, line and column before anything is written, so a
partner fixes a file once instead of one error per run. Extra columns are ignored.
"""
from __future__ import annotations

import csv
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

MAX_ERRORS_PER_FILE = 25

TRUE = {"true", "t", "1", "yes", "y"}
FALSE = {"false", "f", "0", "no", "n"}


def _str(v: str) -> str:
    return v


def _int(v: str) -> int:
    f = float(v)
    if f != int(f):
        raise ValueError("expected a whole number")
    return int(f)


def _nonneg_int(v: str) -> int:
    n = _int(v)
    if n < 0:
        raise ValueError("must be >= 0")
    return n


def _pos_int(v: str) -> int:
    n = _int(v)
    if n <= 0:
        raise ValueError("must be > 0")
    return n


def _float(v: str) -> float:
    return float(v)


def _nonneg_float(v: str) -> float:
    f = float(v)
    if f < 0:
        raise ValueError("must be >= 0")
    return f


def _bool(v: str) -> bool:
    low = v.strip().lower()
    if low in TRUE:
        return True
    if low in FALSE:
        return False
    raise ValueError("expected true/false (also accepted: 1/0, yes/no)")


def _date(v: str) -> str:
    """ISO date (YYYY-MM-DD); a timestamp is accepted and truncated to its date."""
    return date.fromisoformat(v.strip()[:10]).isoformat()


def _node_type(v: str) -> str:
    if v not in ("dark_store", "outlet"):
        raise ValueError("expected dark_store (sells online) or outlet (walk-in only)")
    return v


@dataclass(frozen=True)
class Column:
    name: str
    parse: Callable[[str], Any]
    required: bool = True       # the header must have it
    nullable: bool = False      # a blank cell is allowed (becomes None)


PRODUCTS = [
    Column("sku", _str), Column("name", _str), Column("category", _str), Column("pack_size", _str, nullable=True),
    Column("pack_weight_g", _nonneg_int, nullable=True), Column("unit_cost", _nonneg_float), Column("list_price", _nonneg_float),
    # Blank -> the tenant config's margin_floor_pct for the category (config/tenant.<name>.toml).
    Column("margin_floor_pct", _float, nullable=True),
    Column("shelf_life_days", _pos_int), Column("is_food", _bool),
]
BATCHES = [
    Column("batch_id", _str), Column("sku", _str), Column("node_id", _str), Column("qty_on_hand", _nonneg_int),
    # Blank expiry = a non-perishable lot: never a write-off or sell-by gap.
    Column("expiry_date", _date, nullable=True), Column("received_at", _date, nullable=True), Column("source", _str, nullable=True),
]
SALES = [
    Column("date", _date), Column("sku", _str), Column("node_id", _str), Column("units", _nonneg_int),
    Column("revenue", _nonneg_float, nullable=True), Column("on_promo", _bool),
]
# Optional. Without it every node_id is treated as one online dark store in a single cluster.
NODES = [
    Column("node_id", _str), Column("type", _node_type), Column("lead_time_days", _nonneg_int), Column("cluster_id", _str),
    Column("lat", _float, required=False, nullable=True), Column("lng", _float, required=False, nullable=True),
]
# Optional. Without it Sense sees no purchase orders in flight, so stockout risk is overstated.
INBOUND = [
    Column("po_id", _str), Column("sku", _str), Column("node_id", _str), Column("qty", _nonneg_int), Column("eta", _date),
]

CONTRACT = {"products": PRODUCTS, "inventory_batches": BATCHES, "sales": SALES, "nodes": NODES, "inbound": INBOUND}


class ContractError(Exception):
    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__("\n".join(problems))


def read_csv(path: str | Path, columns: list[Column], allow_empty: bool = False) -> tuple[list[dict[str, Any]], list[str]]:
    """Parse one file against its columns. Returns (rows, problems); rows is empty when the
    header itself is wrong, since every later line would repeat the same error."""
    path = Path(path)
    problems: list[str] = []
    if not path.is_file():
        return [], [f"{path}: file not found"]
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        header = [h.strip() for h in (reader.fieldnames or [])]
        reader.fieldnames = header
        missing = [c.name for c in columns if c.required and c.name not in header]
        if missing:
            want = ", ".join(c.name for c in columns if c.required)
            return [], [f"{path}: missing required column(s) {', '.join(missing)}; header has [{', '.join(header)}]; the contract needs [{want}]"]
        present = [c for c in columns if c.name in header]
        rows: list[dict[str, Any]] = []
        for line_no, raw in enumerate(reader, start=2):
            row: dict[str, Any] = {}
            for c in present:
                cell = (raw.get(c.name) or "").strip()
                if cell == "":
                    if c.nullable:
                        row[c.name] = None
                        continue
                    problems.append(f"{path}:{line_no}: column {c.name!r} is blank")
                    continue
                try:
                    row[c.name] = c.parse(cell)
                except ValueError as e:
                    problems.append(f"{path}:{line_no}: column {c.name!r} value {cell!r}: {e}")
            rows.append(row)
            if len(problems) >= MAX_ERRORS_PER_FILE:
                problems.append(f"{path}: stopped after {MAX_ERRORS_PER_FILE} problems")
                break
    if not rows and not problems and not allow_empty:
        problems.append(f"{path}: no data rows")
    return rows, problems
