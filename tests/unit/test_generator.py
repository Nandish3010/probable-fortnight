import hashlib
import json
from datetime import date
from pathlib import Path

import pytest

from agents.gate.store import LocalStore
from data.generator import AS_OF, generate
from data.generator.catalog import FORBIDDEN_WORDS


def _hashes(d: Path) -> dict[str, str]:
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(d.glob("*.jsonl"))}


@pytest.mark.slow
def test_seeded_run_is_byte_identical(tmp_path: Path):
    a, b = tmp_path / "a", tmp_path / "b"
    generate(a, seed=7)
    generate(b, seed=7)
    assert _hashes(a) == _hashes(b)
    assert (a / "manifest.json").read_text() == (b / "manifest.json").read_text()


def test_row_counts_and_planted_situations(base_store: LocalStore):
    m = json.loads((base_store.root / "manifest.json").read_text())
    c = m["counts"]
    assert c["products"] == 300 and c["nodes"] == 16 and c["customers"] == 4000
    nodes = base_store.read("nodes")
    assert sum(n["type"] == "dark_store" for n in nodes) == 10 and sum(n["type"] == "outlet" for n in nodes) == 6
    batches = {b["batch_id"]: b for b in base_store.read("inventory_batches")}
    chips = batches["B-CHIPS-DS07-01"]
    assert chips["node_id"] == "DS-07" and (date.fromisoformat(chips["online_sellby_date"]) - AS_OF).days == 6
    assert (date.fromisoformat(chips["expiry_date"]) - AS_OF).days == 51
    assert batches["B-TEA-DS04-01"]["node_id"] == "DS-04"
    assert batches["B-QUINOA-OUT02-01"]["node_id"] == "OUT-02"
    assert batches["B-COLAZERO-DS07-01"]["qty_on_hand"] == 0
    assert {"B-KAJU-DS-01-01", "B-KAJU-DS-03-01"} <= set(batches)


def test_sellby_never_after_expiry_and_no_pet_skus(base_store: LocalStore):
    products = {p["sku"]: p for p in base_store.read("products")}
    for b in base_store.read("inventory_batches"):
        if products[b["sku"]]["is_food"]:
            assert b["online_sellby_date"] <= b["expiry_date"], b
    for p in products.values():
        assert not any(w in p["name"].lower() for w in FORBIDDEN_WORDS), p


def test_consent_covers_every_customer(base_store: LocalStore):
    ids = {c["customer_id"] for c in base_store.read("customers")}
    covered = {r["customer_id"] for r in base_store.read("consent") if r["purpose"] == "marketing"}
    assert ids <= covered


def test_daily_series_follow_the_stated_rule(base_store: LocalStore):
    """Weekend days carry more units than Tuesdays on average (day-of-week profile), and every
    (date, sku, node) appears at most once."""
    rows = base_store.read("sales_daily")
    seen = set()
    by_dow = [0.0] * 7
    n_dow = [0] * 7
    for r in rows:
        key = (r["date"], r["sku"], r["node_id"])
        assert key not in seen
        seen.add(key)
        d = date.fromisoformat(r["date"]).weekday()
        by_dow[d] += r["units"]
        n_dow[d] += 1
    avg = [by_dow[i] / max(1, n_dow[i]) for i in range(7)]
    assert avg[5] > avg[1] and avg[6] > avg[1]
