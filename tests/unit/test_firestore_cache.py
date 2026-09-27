"""agents.gate.firestore_cache: pure-logic tests against a fake Firestore client (tests/
fake_firestore.py) -- this repo's unit tests never touch real GCP credentials or network. The
real mirror-then-read round trip against amru-509214's Firestore Native database was first
verified in eval/raw/firestore_cache_2026-09-24/summary.json. The two-visitor overlay test (one
approves a play, one does not) is tests/agents/test_serving_cache_overlay.py; it needs the tenant.
"""
from __future__ import annotations

import json
from datetime import date

import pytest

from agents.gate import firestore_cache as fc
from agents.gate.firestore_cache import (
    FirestoreCache,
    ServingReads,
    firestore_cache_enabled,
    snapshot_id,
)
from agents.gate.store import LocalStore, OverlayStore
from tests.fake_firestore import FakeClient

AS_OF = date(2026, 9, 12)


def test_firestore_cache_enabled_reads_env(monkeypatch):
    monkeypatch.delenv("TAAL_SERVING_CACHE", raising=False)
    assert firestore_cache_enabled() is False
    monkeypatch.setenv("TAAL_SERVING_CACHE", "firestore")
    assert firestore_cache_enabled() is True
    monkeypatch.setenv("TAAL_SERVING_CACHE", "local")
    assert firestore_cache_enabled() is False


def _batches():
    return [
        {"sku": "CHIPS-01", "node_id": "DS-07", "qty_on_hand": 10, "expiry_date": "2026-12-01", "online_sellby_date": "2026-10-01", "batch_id": "B-1"},
        {"sku": "CHIPS-01", "node_id": "DS-07", "qty_on_hand": 5, "expiry_date": "2026-11-01", "online_sellby_date": "2026-09-25", "batch_id": "B-2"},
        {"sku": "CHIPS-01", "node_id": "DS-07", "qty_on_hand": 3, "expiry_date": "2026-08-01", "online_sellby_date": "2026-07-01", "batch_id": "B-expired"},
    ]


def test_mirror_stock_aggregates_unexpired_batches_and_stamps_as_of_and_snapshot():
    cache = FirestoreCache(FakeClient(), "kutumb-mart")
    n = cache.mirror_stock(_batches(), {"CHIPS-01": {"name": "Masala Chips", "list_price": 40}}, date(2026, 9, 20), "snap-1")
    assert n == 1  # one (sku, node) pair
    doc = cache.get_stock("CHIPS-01", "DS-07")
    assert doc["qty"] == 15  # the expired batch (expiry 2026-08-01 < as_of) excluded
    assert doc["online_sellby_date"] == "2026-09-25"
    assert doc["name"] == "Masala Chips"
    assert doc["as_of"] == "2026-09-20" and doc["snapshot_id"] == "snap-1"


def test_mirror_stock_zeroes_qty_once_online_sellby_has_passed():
    cache = FirestoreCache(FakeClient(), "kutumb-mart")
    batches = [{"sku": "TEA-01", "node_id": "DS-01", "qty_on_hand": 20, "expiry_date": "2026-12-01", "online_sellby_date": "2026-09-01", "batch_id": "B-1"}]
    cache.mirror_stock(batches, {}, date(2026, 9, 20), "snap-1")
    assert cache.get_stock("TEA-01", "DS-01")["qty"] == 0


def test_mirror_customers_carries_profile_only_never_consent():
    cache = FirestoreCache(FakeClient(), "kutumb-mart")
    cache.mirror_customers([{"customer_id": "CUST-MEENA", "home_node_id": "DS-07", "language": "kn"}], AS_OF, "snap-1")
    doc = cache.get_customer("CUST-MEENA")
    assert doc["home_node_id"] == "DS-07" and doc["language"] == "kn"
    assert not any("consent" in k for k in doc), "consent changes per visitor on STOP; it must never be in the tenant-wide cache"


def test_there_is_no_cache_reader_for_consent_or_offers():
    # Both change per visitor (Approve writes offers, STOP withdraws consent): the only readers
    # the chat tools can reach are stock() and customer().
    for name in ("get_consent", "get_offers", "consent", "offers"):
        assert not hasattr(FirestoreCache, name) and not hasattr(ServingReads, name), name


def _tenant(tmp_path):
    base = tmp_path / "base"
    base.mkdir()
    (base / "manifest.json").write_text(json.dumps({"as_of": AS_OF.isoformat()}))
    store = LocalStore(base)
    store.write("inventory_batches", _batches())
    store.write("customers", [{"customer_id": "CUST-MEENA", "home_node_id": "DS-07", "language": "kn"}])
    store.write("products", [{"sku": "CHIPS-01", "name": "Masala Chips", "list_price": 40}])
    return base


def _mirrored(base, as_of=AS_OF, snap=None):
    cache = FirestoreCache(FakeClient(), "kutumb-mart")
    snap = snap or snapshot_id(base)
    cache.mirror_stock(LocalStore(base).read("inventory_batches"), {"CHIPS-01": {"name": "Masala Chips", "list_price": 40}}, as_of, snap)
    cache.mirror_customers(LocalStore(base).read("customers"), as_of, snap)
    return cache


@pytest.fixture(autouse=True)
def _fresh_stats():
    fc.STATS.reset()
    yield
    fc.STATS.reset()


def test_serving_reads_hit_when_date_and_snapshot_match(tmp_path):
    base = _tenant(tmp_path)
    reads = ServingReads(_mirrored(base), LocalStore(base), AS_OF, AS_OF)
    doc = reads.stock("CHIPS-01", "DS-07")
    assert doc is not None and doc["qty"] == 15 and "as_of" not in doc and "snapshot_id" not in doc
    assert reads.customer("CUST-MEENA")["home_node_id"] == "DS-07"
    assert fc.STATS.snapshot()["hit"] == 2


def test_serving_reads_rejects_a_doc_mirrored_on_another_date(tmp_path):
    """A mirror run on a real calendar date would serve expiry math weeks off the pinned demo."""
    base = _tenant(tmp_path)
    reads = ServingReads(_mirrored(base, as_of=date(2026, 9, 27)), LocalStore(base), AS_OF, AS_OF)
    assert reads.stock("CHIPS-01", "DS-07") is None
    assert fc.STATS.snapshot()["stale"] == 1


def test_serving_reads_rejects_when_service_clock_is_not_the_snapshot_date(tmp_path):
    base = _tenant(tmp_path)
    reads = ServingReads(_mirrored(base), LocalStore(base), date(2026, 9, 27), AS_OF)
    assert reads.stock("CHIPS-01", "DS-07") is None


def test_serving_reads_rejects_a_doc_from_another_snapshot(tmp_path):
    base = _tenant(tmp_path)
    reads = ServingReads(_mirrored(base, snap="some-other-seed"), LocalStore(base), AS_OF, AS_OF)
    assert reads.customer("CUST-MEENA") is None
    assert fc.STATS.snapshot()["stale"] == 1


def test_snapshot_id_changes_when_a_mirrored_base_file_changes(tmp_path):
    base = _tenant(tmp_path)
    before = snapshot_id(base)
    LocalStore(base).append("inventory_batches", [{"sku": "X", "node_id": "DS-01", "qty_on_hand": 1, "expiry_date": None, "batch_id": "B-9"}])
    assert snapshot_id(base) != before


def test_serving_reads_bypasses_cache_for_an_overlaid_table(tmp_path):
    base = _tenant(tmp_path)
    cache = _mirrored(base)
    visitor = OverlayStore(base, tmp_path / "sandbox" / "v-ordered")
    visitor.append("order_lines", [{"customer_id": "CUST-MEENA", "sku": "CHIPS-01", "qty": 1}])
    reads = ServingReads(cache, visitor, AS_OF, AS_OF)
    assert reads.stock("CHIPS-01", "DS-07") is None, "a visitor with their own order_lines must read their own store"
    assert reads.customer("CUST-MEENA") is not None, "customers not overlaid: the profile is still safe to serve"
    s = fc.STATS.snapshot()
    assert s["overlay"] == 1 and s["hit"] == 1


def test_serving_reads_fails_open_and_trips_the_breaker(tmp_path):
    base = _tenant(tmp_path)
    cache = _mirrored(base)
    cache._client.fail_reads = True
    reads = ServingReads(cache, LocalStore(base), AS_OF, AS_OF)
    assert reads.stock("CHIPS-01", "DS-07") is None
    reads_before = cache._client.reads
    assert reads.stock("CHIPS-01", "DS-07") is None
    assert cache._client.reads == reads_before, "breaker open: no second Firestore read for 60 s"
    s = fc.STATS.snapshot()
    assert s["error"] == 1 and s["breaker"] == 1


def test_mirror_refuses_when_clock_and_snapshot_disagree(tmp_path, monkeypatch):
    base = _tenant(tmp_path)
    monkeypatch.setenv("TAAL_NOW", "2026-09-27T03:30:00Z")
    with pytest.raises(SystemExit, match="refusing to mirror"):
        fc.mirror(base, FirestoreCache(FakeClient(), "kutumb-mart"))


def test_mirror_is_idempotent_and_writes_meta(tmp_path, monkeypatch):
    base = _tenant(tmp_path)
    monkeypatch.setenv("TAAL_NOW", "2026-09-12T03:30:00Z")
    client = FakeClient()
    first = fc.mirror(base, FirestoreCache(client, "kutumb-mart"))
    docs_after_first = dict(client.docs)
    second = fc.mirror(base, FirestoreCache(client, "kutumb-mart"))
    assert first["snapshot_id"] == second["snapshot_id"] and first["stock_docs"] == 1 and first["customer_docs"] == 1
    assert {k: v for k, v in client.docs.items() if k[0] != "serving_meta"} == {k: v for k, v in docs_after_first.items() if k[0] != "serving_meta"}
    meta = FirestoreCache(client, "kutumb-mart").get_meta()
    assert meta["as_of"] == "2026-09-12" and meta["snapshot_id"] == first["snapshot_id"]


def test_a_client_that_cannot_be_built_fails_open_to_the_store(tmp_path, monkeypatch):
    """Found live-locally: TAAL_SERVING_CACHE=firestore with unusable credentials made every
    /chat a 500, because client construction happened outside the read's try/except."""
    base = _tenant(tmp_path)
    monkeypatch.setenv("TAAL_SERVING_CACHE", "firestore")

    def boom(*a, **k):
        raise RuntimeError("no credentials (fake)")

    monkeypatch.setattr(fc, "build_cache", boom)
    assert fc.serving_reads(LocalStore(base), "2026-09-12T09:00:00Z", AS_OF, "kutumb-mart") is None
    assert fc.STATS.snapshot()["error"] == 1
