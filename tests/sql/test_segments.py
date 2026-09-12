from agents.customer.context import CustomerContext, reset_context, set_context
from agents.customer.tools import find_substitutes
from agents.gate.store import LocalStore


def test_kmeans_six_segments_every_customer_assigned(base_store: LocalStore):
    segs = base_store.read("segments")
    assert len(segs) == 6 and all(s["k"] == 6 for s in segs)
    ids = {s["segment_id"] for s in segs}
    assert all(c["segment_id"] in ids for c in base_store.read("customers"))
    assert all(s["name"] and not s["name"].startswith("seg_") for s in segs), "names are human-readable"


def test_substitutes_same_category_top5(base_store: LocalStore):
    products = {p["sku"]: p["category"] for p in base_store.read("products")}
    rows = base_store.read("substitutes")
    assert len(rows) == len(products)
    for r in rows:
        assert len(r["candidates"]) <= 5
        assert all(products[c] == products[r["sku"]] for c in r["candidates"])


def test_affinity_exists_per_customer(base_store: LocalStore):
    have = {a["customer_id"] for a in base_store.read("affinity")}
    assert len(have) >= 0.99 * len(base_store.read("customers"))


def test_find_substitutes_filters_zero_stock(base_store: LocalStore):
    ctx = CustomerContext.build(base_store, "CUST-MEENA", "2026-09-12T09:00:00Z")
    tok = set_context(ctx)
    try:
        subs = find_substitutes("SKU-COLA-ZERO-500ML", "DS-07")
        assert subs and all(s["qty"] > 0 for s in subs) and len(subs) <= 5
        assert all(s["sku"] != "SKU-COLA-ZERO-500ML" for s in subs)
    finally:
        reset_context(tok)
