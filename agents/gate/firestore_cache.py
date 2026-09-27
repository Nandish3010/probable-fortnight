"""Firestore serving cache for chat-time reads -- item 5 of the "make the architecture true"
review. `get_stock`, `find_substitutes` and `get_customer_context` in `agents/customer/tools.py`
otherwise re-read the store on every lookup (`_stock_info` walks every row of
`inventory_batches`). The store stays the system of record; Firestore holds a serving copy of the
two things that cannot differ between visitors, shaped like DECISIONS.md §3.3's collections:
`stock/{node}/skus/{sku}` and `customers/{id}` (profile only).

Behind its own opt-in (`TAAL_SERVING_CACHE=firestore`), never tied to `TAAL_MODEL_BACKEND` or
`TAAL_SESSION_BACKEND`: with the flag unset, `build_cache()` returns None and every chat-time read
goes to the store exactly as before.

Three rules make a tenant-wide cache safe to serve to per-visitor sandboxes (`ServingReads`, the
one helper the chat tools call):
1. Overlay-aware. A visitor's OverlayStore can diverge from the base tenant. Stock is served from
   the cache only when the visitor has no overlay rows in `inventory_batches` / `order_lines`, a
   customer profile only when they have none in `customers`. Consent and offers change per
   visitor on Approve and STOP, so they are never served from the cache at all -- there is no
   reader for them here.
2. Clock-safe. Every mirrored doc carries `as_of` (the date its expiry / sell-by math used) and
   `snapshot_id` (a hash of the base files it was computed from). A doc is served only when its
   `as_of` equals both the service's own clock date (TAAL_NOW on the served demo) and the
   tenant's manifest `as_of`, and its `snapshot_id` equals the serving image's base snapshot.
   Anything else falls back to the store: a mirror run on a real calendar date, or from another
   seed, is rejected rather than served.
3. Fail-open to the store. A Firestore error or a >1 s read turns the cache off for 60 s and the
   turn reads the store; the cache can cost at most one slow read, never a failed turn.

The mirror runs from the same seeded snapshot the image serves (`python -m
agents.gate.firestore_cache --mirror`, a one-off Cloud Run job in infra/deploy.sh), never from the
nightly BigQuery job, whose dates are real ones.

First verified against a real Firestore Native database in
`eval/raw/firestore_cache_2026-09-24/summary.json` (pre-overlay-rules version of this module).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import threading
import time
from collections import defaultdict
from datetime import UTC, date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

# Tables whose overlay rows make a visitor's view differ from the mirrored doc.
STOCK_SOURCE_TABLES = ("inventory_batches", "order_lines")
CUSTOMER_SOURCE_TABLES = ("customers",)
# Base files every mirrored doc is computed from; their hash is the snapshot id.
SNAPSHOT_FILES = ("manifest.json", "inventory_batches.jsonl", "products.jsonl", "customers.jsonl")
META_COLLECTION = "serving_meta"
READ_TIMEOUT_S = 1.0
BREAKER_S = 60.0


def firestore_cache_enabled() -> bool:
    return os.environ.get("TAAL_SERVING_CACHE") == "firestore"


@lru_cache(maxsize=8)
def _snapshot_id_cached(root: str, stamp: tuple[tuple[str, int, int], ...]) -> str:
    h = hashlib.sha256()
    for name, _, _ in stamp:
        p = Path(root) / name
        h.update(name.encode())
        h.update(p.read_bytes() if p.exists() else b"")
    return h.hexdigest()[:16]


def snapshot_id(root: str | Path) -> str:
    """Hash of the base files the mirror reads. Recomputed only when one of them changes
    (size or mtime), so a chat turn pays a stat() per file, not a re-hash."""
    root = Path(root)
    stamp = tuple((n, (root / n).stat().st_size, (root / n).stat().st_mtime_ns) if (root / n).exists() else (n, -1, -1) for n in SNAPSHOT_FILES)
    return _snapshot_id_cached(str(root.resolve()), stamp)


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
    is a plain doc get/set; the aggregation in `_stock_doc` runs at mirror time, not read time."""

    def __init__(self, client: Any, tenant_id: str):
        self._client = client
        self._tenant_id = tenant_id

    # ---- mirror (write path; the deploy-time mirror job, never a chat turn) ----

    def _set_all(self, refs_and_docs: list[tuple[Any, dict[str, Any]]]) -> None:
        batch_fn = getattr(self._client, "batch", None)
        if batch_fn is None:
            for ref, doc in refs_and_docs:
                ref.set(doc)
            return
        for i in range(0, len(refs_and_docs), 450):  # Firestore caps a batch at 500 writes
            batch = batch_fn()
            for ref, doc in refs_and_docs[i:i + 450]:
                batch.set(ref, doc)
            batch.commit()

    def mirror_stock(self, batches: list[dict[str, Any]], products: dict[str, dict[str, Any]], as_of: date, snapshot: str) -> int:
        by_pair: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        for b in batches:
            by_pair[(b["sku"], b["node_id"])].append(b)
        writes = []
        for (sku, node_id), rows in sorted(by_pair.items()):
            doc = _stock_doc(sku, node_id, rows, products, as_of) | {"as_of": as_of.isoformat(), "snapshot_id": snapshot}
            writes.append((self._client.collection("stock").document(node_id).collection("skus").document(sku), doc))
        self._set_all(writes)
        return len(writes)

    def mirror_customers(self, customers: list[dict[str, Any]], as_of: date, snapshot: str) -> int:
        """Profile only. Consent is deliberately not mirrored: it changes per visitor on STOP."""
        writes = []
        for c in customers:
            doc = {
                "customer_id": c["customer_id"], "home_node_id": c["home_node_id"],
                "language": c.get("language", "en"), "display_name": c.get("display_name"),
                "as_of": as_of.isoformat(), "snapshot_id": snapshot,
            }
            writes.append((self._client.collection("customers").document(c["customer_id"]), doc))
        self._set_all(writes)
        return len(writes)

    def write_meta(self, as_of: date, snapshot: str, counts: dict[str, int], mirrored_at: str) -> None:
        self._client.collection(META_COLLECTION).document(self._tenant_id).set({"as_of": as_of.isoformat(), "snapshot_id": snapshot, "counts": counts, "mirrored_at": mirrored_at})

    # ---- raw reads (callers go through ServingReads, which applies the rules above) ----

    def get_stock(self, sku: str, node_id: str) -> dict[str, Any] | None:
        snap = self._client.collection("stock").document(node_id).collection("skus").document(sku).get(timeout=READ_TIMEOUT_S)
        return snap.to_dict() if snap.exists else None

    def get_customer(self, customer_id: str) -> dict[str, Any] | None:
        snap = self._client.collection("customers").document(customer_id).get(timeout=READ_TIMEOUT_S)
        return snap.to_dict() if snap.exists else None

    def get_meta(self) -> dict[str, Any] | None:
        snap = self._client.collection(META_COLLECTION).document(self._tenant_id).get(timeout=READ_TIMEOUT_S)
        return snap.to_dict() if snap.exists else None


class _Stats:
    """Process-wide counters for /health and the latency evidence. `hit` = served from Firestore;
    `miss` = no doc; `stale` = doc rejected by the as_of/snapshot rule; `overlay` = visitor has
    overlay rows in a source table, cache not consulted; `error` = Firestore failed or timed out."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.counts: dict[str, int] = defaultdict(int)
        self.read_ms: list[float] = []
        self.disabled_until = 0.0

    def bump(self, key: str, ms: float | None = None) -> None:
        with self._lock:
            self.counts[key] += 1
            if ms is not None:
                self.read_ms.append(ms)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            c = dict(self.counts)
            ms = sorted(self.read_ms)
        consulted = c.get("hit", 0) + c.get("miss", 0) + c.get("stale", 0) + c.get("error", 0)
        lookups = consulted + c.get("overlay", 0) + c.get("breaker", 0)
        return {**c, "lookups": lookups, "hit_rate": round(c.get("hit", 0) / lookups, 4) if lookups else None, "firestore_reads": consulted,
                "read_ms_p50": ms[len(ms) // 2] if ms else None, "read_ms_p95": ms[min(len(ms) - 1, int(0.95 * len(ms)))] if ms else None}

    def reset(self) -> None:
        with self._lock:
            self.counts.clear()
            self.read_ms.clear()
            self.disabled_until = 0.0


STATS = _Stats()


def _overlaid(store: Any, tables: tuple[str, ...]) -> bool:
    """True when this visitor's sandbox has its own copy of any of `tables` (OverlayStore writes
    copy the whole base table into the overlay first, so file existence is the test)."""
    return hasattr(store, "base") and any((Path(store.root) / f"{t}.jsonl").exists() for t in tables)


class ServingReads:
    """The one helper the chat tools call. `stock()` / `customer()` return a cached doc only when
    it is safe for THIS visitor, else None -- meaning "read your own store". There is no consent
    or offers reader on purpose: those are always read from the visitor's store."""

    def __init__(self, cache: FirestoreCache, store: Any, today: date, as_of: date):
        self._cache = cache
        self._store = store
        self._today = today.isoformat()
        self._as_of = as_of.isoformat()
        base = store.base.root if hasattr(store, "base") else store.root
        self._snapshot = snapshot_id(base)

    def _fresh(self, doc: dict[str, Any]) -> bool:
        return doc.get("as_of") == self._today == self._as_of and doc.get("snapshot_id") == self._snapshot

    def _read(self, tables: tuple[str, ...], fetch: Any) -> dict[str, Any] | None:
        if _overlaid(self._store, tables):
            STATS.bump("overlay")
            return None
        if time.monotonic() < STATS.disabled_until:
            STATS.bump("breaker")
            return None
        t0 = time.perf_counter()
        try:
            doc = fetch()
        except Exception:
            STATS.bump("error")
            STATS.disabled_until = time.monotonic() + BREAKER_S
            return None
        ms = (time.perf_counter() - t0) * 1000.0
        if ms > READ_TIMEOUT_S * 1000.0:
            STATS.disabled_until = time.monotonic() + BREAKER_S
        if doc is None:
            STATS.bump("miss", ms)
            return None
        if not self._fresh(doc):
            STATS.bump("stale", ms)
            return None
        STATS.bump("hit", ms)
        return {k: v for k, v in doc.items() if k not in ("as_of", "snapshot_id")}

    def stock(self, sku: str, node_id: str) -> dict[str, Any] | None:
        return self._read(STOCK_SOURCE_TABLES, lambda: self._cache.get_stock(sku, node_id))

    def customer(self, customer_id: str) -> dict[str, Any] | None:
        return self._read(CUSTOMER_SOURCE_TABLES, lambda: self._cache.get_customer(customer_id))


@lru_cache(maxsize=4)
def _client(project: str) -> Any:
    """One Firestore client per process: building one per chat turn costs a channel setup."""
    from google.cloud import firestore

    return firestore.Client(project=project)


def build_cache(tenant_id: str | None = None, project: str | None = None) -> FirestoreCache | None:
    """The entry point agents/customer/context.py and the mirror job call. Returns None (read the
    store directly, unchanged) unless TAAL_SERVING_CACHE=firestore is explicitly set."""
    if not firestore_cache_enabled():
        return None
    proj = project or os.environ.get("GOOGLE_CLOUD_PROJECT", "amru-509214")
    return FirestoreCache(_client(proj), tenant_id or "kutumb-mart")


def serving_reads(store: Any, now_iso: str, as_of: date, tenant_id: str) -> ServingReads | None:
    """Per-turn reader, or None (read the store). Fails open like a read does: a client that
    cannot even be built (no credentials, bad project) must cost the turn nothing but the cache,
    never a 500 -- found by running a local API with the flag on and no credentials."""
    if not firestore_cache_enabled():
        return None
    if time.monotonic() < STATS.disabled_until:
        return None
    try:
        cache = build_cache(tenant_id)
    except Exception:
        STATS.bump("error")
        STATS.disabled_until = time.monotonic() + BREAKER_S
        return None
    if cache is None:
        return None
    return ServingReads(cache, store, date.fromisoformat(now_iso[:10]), as_of)


def _clock_date() -> date:
    """Same rule as services/api/main.py::_now(): TAAL_NOW when pinned, else the wall clock."""
    pinned = os.environ.get("TAAL_NOW")
    if pinned:
        return datetime.fromisoformat(pinned.replace("Z", "+00:00")).astimezone(UTC).date()
    return datetime.now(UTC).date()


def mirror(data_dir: str | Path, cache: FirestoreCache) -> dict[str, Any]:
    """Mirror stock + customer profiles from the seeded snapshot at `data_dir`. Idempotent (every
    write is a full-document set keyed by id). Refuses when the service clock and the snapshot
    disagree on the date: those docs would be rejected at read time anyway."""
    from agents.gate.store import LocalStore

    store = LocalStore(data_dir)
    manifest = json.loads((Path(data_dir) / "manifest.json").read_text(encoding="utf-8"))
    as_of = date.fromisoformat(manifest["as_of"])
    clock = _clock_date()
    if clock != as_of:
        raise SystemExit(f"refusing to mirror: service clock date {clock} != snapshot as_of {as_of} (set TAAL_NOW to the served demo's pin)")
    snap = snapshot_id(data_dir)
    t0 = time.perf_counter()
    products = {p["sku"]: p for p in store.read("products")}
    counts = {"stock_docs": cache.mirror_stock(store.read("inventory_batches"), products, as_of, snap), "customer_docs": cache.mirror_customers(store.read("customers"), as_of, snap)}
    mirrored_at = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    cache.write_meta(as_of, snap, counts, mirrored_at)
    return {"as_of": as_of.isoformat(), "snapshot_id": snap, **counts, "elapsed_ms": int((time.perf_counter() - t0) * 1000), "mirrored_at": mirrored_at}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Mirror the served demo snapshot into the Firestore serving cache.")
    ap.add_argument("--mirror", action="store_true", required=True)
    ap.add_argument("--data-dir", default=os.environ.get("TAAL_DATA_DIR", ".local/data"))
    ap.add_argument("--tenant", default=None, help="defaults to the tenant in TAAL_TENANT_CONFIG")
    args = ap.parse_args(argv)
    if args.tenant is None:
        from agents.gate.config import load_tenant

        args.tenant = load_tenant().tenant_id
    proj = os.environ.get("GOOGLE_CLOUD_PROJECT", "amru-509214")
    result = mirror(args.data_dir, FirestoreCache(_client(proj), args.tenant))
    json.dump(result, sys.stdout)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
