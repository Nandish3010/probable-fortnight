import json
from datetime import date, timedelta
from pathlib import Path

import jsonschema

from agents.gate.config import load_tenant
from agents.gate.sellby import online_sellby_date
from agents.gate.store import LocalStore
from jobs.sense.gaps import detect

ROOT = Path(__file__).resolve().parents[2]
GAP_SCHEMA = json.loads((ROOT / "docs" / "schemas" / "gap.schema.json").read_text())


def test_rupees_recomputed_independently(base_store: LocalStore):
    products = {p["sku"]: p for p in base_store.read("products")}
    for g in base_store.read("gaps"):
        p = products[g["sku"]]
        expected = g["units_at_risk"] * (p["list_price"] - p["unit_cost"]) if g["type"] == "stockout_risk" else g["units_at_risk"] * p["unit_cost"]
        assert abs(expected - g["rupees_at_stake"]) <= 1.0, g["gap_id"]


def test_all_five_types_with_correct_deadline_types(base_store: LocalStore):
    gaps = base_store.read("gaps")
    types = {g["type"] for g in gaps}
    assert types == {"online_sellby_breach", "expiry_writeoff", "stockout_risk", "rebalance", "slow_mover"}
    for g in gaps:
        if g["type"] == "online_sellby_breach":
            assert g["deadline_type"] == "online_sellby"
        if g["type"] == "stockout_risk":
            assert g["deadline_type"] == "lead_time"
        jsonschema.validate(g, GAP_SCHEMA, format_checker=jsonschema.FormatChecker())


def test_online_sellby_gap_uses_the_versioned_rule(base_store: LocalStore):
    tenant = load_tenant()
    products = {p["sku"]: p for p in base_store.read("products")}
    batches = {b["batch_id"]: b for b in base_store.read("inventory_batches")}
    for g in base_store.read("gaps"):
        if g["type"] != "online_sellby_breach":
            continue
        assert g["evidence"]["sellby_rule"] == tenant.sellby_rule.version
        b = batches[g["batch_id"]]
        p = products[g["sku"]]
        assert g["deadline_date"] == online_sellby_date(date.fromisoformat(b["expiry_date"]), p["shelf_life_days"], tenant.sellby_rule, p["is_food"]).isoformat()


def test_planted_gaps_present(base_store: LocalStore):
    ids = {g["gap_id"]: g for g in base_store.read("gaps")}
    assert ids["gap_chips_ds07"]["units_at_risk"] == 368 and ids["gap_chips_ds07"]["rupees_at_stake"] == 9200.0
    assert ids["gap_tea_ds04"]["type"] == "online_sellby_breach"
    assert ids["gap_cola_ds07"]["type"] == "stockout_risk" and ids["gap_cola_ds02"]["type"] == "stockout_risk"
    assert ids["gap_kaju_ds01"]["type"] == "stockout_risk" and ids["gap_kaju_ds03"]["type"] == "stockout_risk"
    assert ids["gap_quinoa_out02"]["type"] == "slow_mover"


def test_batch_past_sellby_never_yields_an_online_gap(base_store: LocalStore, tmp_path):
    """Plant a lot whose online sell-by passed yesterday but expires inside the horizon."""
    import shutil

    for t in ("products", "nodes", "inventory_batches", "inbound", "forecasts", "manifest"):
        src = base_store.root / (f"{t}.jsonl" if t != "manifest" else "manifest.json")
        shutil.copy(src, tmp_path / src.name)
    store = LocalStore(tmp_path)
    as_of = date.fromisoformat(json.loads((tmp_path / "manifest.json").read_text())["as_of"])
    rows = store.read("inventory_batches")
    rows.append({"tenant_id": "kutumb-mart", "batch_id": "B-PAST-SELLBY", "sku": "SKU-MASALA-CHIPS-200G", "node_id": "DS-08", "qty_on_hand": 500, "expiry_date": (as_of + timedelta(days=10)).isoformat(), "online_sellby_date": (as_of - timedelta(days=1)).isoformat(), "received_at": as_of.isoformat(), "source": "system", "capture_ref": None, "sellby_rule_version": "v1-strict"})
    store.write("inventory_batches", rows)
    gaps = detect(store, store.read("forecasts"), as_of, load_tenant(), "test-run")
    mine = [g for g in gaps if g.get("batch_id") == "B-PAST-SELLBY"]
    assert mine and all(g["type"] != "online_sellby_breach" for g in mine)
    assert any(g["type"] == "expiry_writeoff" and g["evidence"]["sellby_passed"] for g in mine)
