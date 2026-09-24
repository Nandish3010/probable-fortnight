"""agents.gate.firestore_cache: pure-logic tests against a fake Firestore client -- this repo's
unit tests never touch real GCP credentials or network (see test_measure_cost.py's own header for
the same convention). The real mirror-then-read round trip against amru-509214's Firestore Native
database was verified separately with a throwaway script; raw evidence:
eval/raw/firestore_cache_2026-09-24/summary.json.
"""
from __future__ import annotations

from agents.gate.firestore_cache import FirestoreCache, firestore_cache_enabled


class _FakeSnapshot:
    def __init__(self, data):
        self._data = data

    @property
    def exists(self):
        return self._data is not None

    def to_dict(self):
        return self._data


class _FakeDocRef:
    def __init__(self, store, path):
        self._store, self._path = store, path

    def set(self, data):
        self._store[self._path] = dict(data)

    def get(self):
        return _FakeSnapshot(self._store.get(self._path))

    def collection(self, name):
        return _FakeCollectionRef(self._store, self._path + (name,))


class _FakeCollectionRef:
    def __init__(self, store, path):
        self._store, self._path = store, path

    def document(self, doc_id):
        return _FakeDocRef(self._store, self._path + (doc_id,))


class _FakeClient:
    def __init__(self):
        self.docs: dict[tuple, dict] = {}

    def collection(self, name):
        return _FakeCollectionRef(self.docs, (name,))


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


def test_mirror_stock_aggregates_unexpired_batches_and_is_read_back():
    client = _FakeClient()
    cache = FirestoreCache(client, "kutumb-mart")
    from datetime import date

    n = cache.mirror_stock(_batches(), {"CHIPS-01": {"name": "Masala Chips", "list_price": 40}}, date(2026, 9, 20))
    assert n == 1  # one (sku, node) pair
    doc = cache.get_stock("CHIPS-01", "DS-07")
    assert doc is not None
    assert doc["qty"] == 15  # the expired batch (expiry 2026-08-01 < as_of) excluded
    assert doc["online_sellby_date"] == "2026-09-25"  # earliest across the two unexpired batches, still not passed
    assert doc["name"] == "Masala Chips"


def test_mirror_stock_zeroes_qty_once_online_sellby_has_passed():
    client = _FakeClient()
    cache = FirestoreCache(client, "kutumb-mart")
    from datetime import date

    batches = [{"sku": "TEA-01", "node_id": "DS-01", "qty_on_hand": 20, "expiry_date": "2026-12-01", "online_sellby_date": "2026-09-01", "batch_id": "B-1"}]
    cache.mirror_stock(batches, {}, date(2026, 9, 20))
    doc = cache.get_stock("TEA-01", "DS-01")
    assert doc["qty"] == 0  # online_sellby_date 2026-09-01 < as_of 2026-09-20


def test_get_stock_returns_none_on_a_cache_miss():
    cache = FirestoreCache(_FakeClient(), "kutumb-mart")
    assert cache.get_stock("UNKNOWN-SKU", "DS-01") is None


def test_mirror_customers_builds_consent_map_and_get_consent_reads_it():
    client = _FakeClient()
    cache = FirestoreCache(client, "kutumb-mart")
    customers = [{"customer_id": "CUST-MEENA", "home_node_id": "DS-07", "language": "kn"}]
    consent = [
        {"customer_id": "CUST-MEENA", "purpose": "marketing", "channel": "web_chat", "withdrawn_at": None},
        {"customer_id": "CUST-MEENA", "purpose": "marketing", "channel": "whatsapp", "withdrawn_at": "2026-09-01T00:00:00"},
    ]
    cache.mirror_customers(customers, consent)
    assert cache.get_consent("CUST-MEENA", "web_chat") is True
    assert cache.get_consent("CUST-MEENA", "whatsapp") is False
    assert cache.get_consent("CUST-MEENA", "app_push") is False  # never granted for this channel


def test_get_consent_returns_none_on_a_cache_miss_not_false():
    # None must mean "ask the store", never get silently treated as consent withdrawn.
    cache = FirestoreCache(_FakeClient(), "kutumb-mart")
    assert cache.get_consent("CUST-UNKNOWN", "web_chat") is None


def test_mirror_offers_groups_by_customer_and_drops_redeemed():
    client = _FakeClient()
    cache = FirestoreCache(client, "kutumb-mart")
    offers = [
        {"customer_id": "CUST-MEENA", "play_id": "play_1", "text": "offer 1"},
        {"customer_id": "CUST-MEENA", "play_id": "play_2", "text": "offer 2", "redeemed_at": "2026-09-01T00:00:00"},
        {"customer_id": "CUST-ARJUN", "play_id": "play_3", "text": "offer 3"},
    ]
    n = cache.mirror_offers(offers)
    assert n == 2  # two distinct customers with at least one un-redeemed offer
    meena_offers = cache.get_offers("CUST-MEENA")
    assert len(meena_offers) == 1
    assert meena_offers[0]["play_id"] == "play_1"


def test_get_offers_returns_empty_list_not_none_on_a_cache_miss():
    cache = FirestoreCache(_FakeClient(), "kutumb-mart")
    assert cache.get_offers("CUST-NEVER-SEEN") == []
