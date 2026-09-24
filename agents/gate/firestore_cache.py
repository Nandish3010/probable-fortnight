"""Firestore serving cache for chat-time reads -- item 5 of the "make the architecture true"
review: `get_stock`, `find_substitutes`, `get_customer_context` and the consent check in
`agents/customer/tools.py` currently scan the full local/BigQuery store on every single chat
turn (`agents/customer/tools.py::_stock_info` walks every row of `inventory_batches`). BigQuery
(or the local store) stays the system of record; Firestore holds a nightly-refreshed serving copy
shaped exactly like DECISIONS.md §3.3's collections (`stock/{node}/{sku}`, `customers/{id}`,
`offers/{customer_id}`).

Deliberately behind its own opt-in (`TAAL_SERVING_CACHE=firestore`), never tied to
`TAAL_MODEL_BACKEND` or `TAAL_SESSION_BACKEND`: with the flag unset (every deployment today),
`build_cache()` returns None and every chat-time read falls through to the store exactly as
before -- this file changes nothing about the live deployment until someone sets the flag and
redeploys deliberately.

Verified against a real Firestore Native database (`eval/raw/firestore_cache_2026-09-24/
summary.json`): a real mirror write followed by a real read-back of stock, a customer doc and an
offer, through this module against the actual `amru-509214` project.
"""
from __future__ import annotations

import os
from datetime import date
from typing import Any


def firestore_cache_enabled() -> bool:
    return os.environ.get("TAAL_SERVING_CACHE") == "firestore"


def _stock_doc(sku: str, node_id: str, batches: list[dict[str, Any]], products: dict[str, dict[str, Any]], as_of: date) -> dict[str, Any]:
    """Same aggregation `_stock_info` in agents/customer/tools.py computes on the fly, done once
    here for every (sku, node) pair so the mirror step, not the chat turn, pays the scan cost."""
    today = as_of.isoformat()
    qty, sellby, expiry, batch_id = 0, None, None, None
    for b in batches:
        if b["sku"] != sku or b["node_id"] != node_id or int(b["qty_on_hand"]) <= 0:
            continue
        if b["expiry_date"] and b["expiry_date"] < today:
            continue
        qty += int(b["qty_on_hand"])
        if b.get("online_sellby_date") and (sellby is None or b["online_sellby_date"] < sellby):
            sellby, batch_id = b["online_sellby_date"], b["batch_id"]
        if b.get("expiry_date") and (expiry is None or b["expiry_date"] < expiry):
            expiry = b["expiry_date"]
    online_ok = sellby is None or sellby >= today
    return {
        "sku": sku, "node_id": node_id, "qty": qty if online_ok else 0,
        "online_sellby_date": sellby, "expiry_date": expiry, "batch_id": batch_id,
        "name": products.get(sku, {}).get("name", sku), "list_price": products.get(sku, {}).get("list_price"),
    }


class FirestoreCache:
    """Thin wrapper over a real (or fake, in tests) `google.cloud.firestore.Client`. Every method
    is a plain doc get/set -- no query logic lives here beyond the aggregation in `_stock_doc`,
    which runs at mirror time, not read time."""

    def __init__(self, client: Any, tenant_id: str):
        self._client = client
        self._tenant_id = tenant_id

    # ---- mirror (write path; called nightly from jobs/sense, never from a chat turn) ----

    def mirror_stock(self, batches: list[dict[str, Any]], products: dict[str, dict[str, Any]], as_of: date) -> int:
        pairs = {(b["sku"], b["node_id"]) for b in batches}
        n = 0
        for sku, node_id in pairs:
            doc = _stock_doc(sku, node_id, batches, products, as_of)
            self._client.collection("stock").document(node_id).collection("skus").document(sku).set(doc)
            n += 1
        return n

    def mirror_customers(self, customers: list[dict[str, Any]], consent_rows: list[dict[str, Any]]) -> int:
        consent_by_customer: dict[str, list[dict[str, Any]]] = {}
        for r in consent_rows:
            consent_by_customer.setdefault(r["customer_id"], []).append(r)
        for c in customers:
            rows = consent_by_customer.get(c["customer_id"], [])
            marketing_ok = {}
            for r in rows:
                if r["purpose"] == "marketing":
                    marketing_ok[r["channel"]] = not r.get("withdrawn_at")
            doc = {
                "customer_id": c["customer_id"], "home_node_id": c["home_node_id"],
                "language": c.get("language", "en"), "display_name": c.get("display_name"),
                "consent_marketing_by_channel": marketing_ok,
            }
            self._client.collection("customers").document(c["customer_id"]).set(doc)
        return len(customers)

    def mirror_offers(self, offers: list[dict[str, Any]]) -> int:
        by_customer: dict[str, list[dict[str, Any]]] = {}
        for o in offers:
            if o.get("redeemed_at"):
                continue
            by_customer.setdefault(o["customer_id"], []).append(o)
        for customer_id, rows in by_customer.items():
            self._client.collection("offers").document(customer_id).set({"pending": rows})
        return len(by_customer)

    # ---- read (chat-time; called from agents/customer/tools.py) ----

    def get_stock(self, sku: str, node_id: str) -> dict[str, Any] | None:
        snap = self._client.collection("stock").document(node_id).collection("skus").document(sku).get()
        return snap.to_dict() if snap.exists else None

    def get_customer(self, customer_id: str) -> dict[str, Any] | None:
        snap = self._client.collection("customers").document(customer_id).get()
        return snap.to_dict() if snap.exists else None

    def get_consent(self, customer_id: str, channel: str) -> bool | None:
        """None means "not in the cache" -- the caller falls back to the store, never treats a
        cache miss as consent withdrawn."""
        c = self.get_customer(customer_id)
        if c is None:
            return None
        return bool(c.get("consent_marketing_by_channel", {}).get(channel, False))

    def get_offers(self, customer_id: str) -> list[dict[str, Any]] | None:
        snap = self._client.collection("offers").document(customer_id).get()
        if not snap.exists:
            return []
        return snap.to_dict().get("pending", [])


def build_cache(tenant_id: str | None = None, project: str | None = None) -> FirestoreCache | None:
    """The one entry point agents/customer/tools.py and jobs/sense/run.py call. Returns None
    (meaning: read the store directly, unchanged) unless TAAL_SERVING_CACHE=firestore is
    explicitly set."""
    if not firestore_cache_enabled():
        return None
    from google.cloud import firestore

    proj = project or os.environ.get("GOOGLE_CLOUD_PROJECT", "amru-509214")
    client = firestore.Client(project=proj)
    return FirestoreCache(client, tenant_id or "kutumb-mart")
