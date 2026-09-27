"""The Firestore serving cache is tenant-wide; judge-mode sandboxes are per visitor. Two visitors
chat as the same treated customer: visitor A approved the play, visitor B did not. With the cache
on, A must see the offer and B must not; A's STOP must not reach B; stock that neither visitor
changed is still served from the cache. Fake Firestore client (tests/fake_firestore.py), stub
model, the real seeded tenant and the real tool code."""
from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from agents.customer.context import CustomerContext, reset_context, set_context
from agents.customer.tools import _consent_ok, _stock_info, get_customer_context, record_stop
from agents.gate import firestore_cache as fc
from agents.gate.config import load_tenant
from agents.gate.firestore_cache import FirestoreCache
from agents.gate.store import OverlayStore
from services.api.approve import approve
from tests.fake_firestore import FakeClient

PLAY = "play_chips_ds07_v1"
NOW_ISO = "2026-09-12T09:05:00Z"


@pytest.fixture
def mirrored(data_dir, monkeypatch):
    monkeypatch.setenv("TAAL_NOW", "2026-09-12T03:30:00Z")
    monkeypatch.setenv("TAAL_SERVING_CACHE", "firestore")
    client = FakeClient()
    tenant = load_tenant()
    fc.mirror(data_dir, FirestoreCache(client, tenant.tenant_id))
    monkeypatch.setattr(fc, "build_cache", lambda tenant_id=None, project=None: FirestoreCache(client, tenant_id or tenant.tenant_id))
    fc.STATS.reset()
    yield client
    fc.STATS.reset()


def _in(store, customer_id, fn, *args):
    ctx = CustomerContext.build(store, customer_id, NOW_ISO, load_tenant(), "web_chat")
    assert ctx.cache is not None, "the serving cache must be active for this test to mean anything"
    token = set_context(ctx)
    try:
        return fn(ctx, *args)
    finally:
        reset_context(token)


def test_one_visitor_approves_the_other_does_not(data_dir, tmp_path, mirrored):
    a = OverlayStore(data_dir, tmp_path / "sandbox" / "visitor-approved")
    b = OverlayStore(data_dir, tmp_path / "sandbox" / "visitor-untouched")
    approve(a, load_tenant(), PLAY, datetime(2026, 9, 12, 9, 0, tzinfo=UTC))

    consenting = {r["customer_id"] for r in a.read("consent") if r["purpose"] == "marketing" and r["channel"] == "web_chat" and not r.get("withdrawn_at")}
    treated = next(r["customer_id"] for r in a.read("play_assignments") if r["play_id"] == PLAY and r["arm"] == "treated" and r["customer_id"] in consenting)

    ctx_a = _in(a, treated, lambda ctx: get_customer_context(treated))
    ctx_b = _in(b, treated, lambda ctx: get_customer_context(treated))
    assert [o["play_id"] for o in ctx_a["pending_offers"]] == [PLAY], "the approving visitor must see their offer"
    assert ctx_b["pending_offers"] == [], "an offer approved in visitor A's sandbox leaked to visitor B"
    assert ctx_a["home_node_id"] == ctx_b["home_node_id"], "the profile is the same for both, and safe to share"

    # Stock at the play's node: neither visitor changed inventory_batches/order_lines, so both are
    # served from the cache, and the cached doc agrees with the visitor's own store scan.
    row = next(p for p in a.read("plays") if p["play_id"] == PLAY)
    play = json.loads(row["play_json"]) if isinstance(row.get("play_json"), str) else row["play_json"]
    sku = play["target"]["sku"]
    before = fc.STATS.snapshot().get("hit", 0)
    cached_a = _in(a, treated, lambda ctx: _stock_info(ctx, sku, "DS-07"))
    cached_b = _in(b, treated, lambda ctx: _stock_info(ctx, sku, "DS-07"))
    assert fc.STATS.snapshot()["hit"] == before + 2
    no_cache = _in(b, treated, lambda ctx: (setattr(ctx, "cache", None), _stock_info(ctx, sku, "DS-07"))[1])
    assert cached_a == cached_b == no_cache

    # STOP in A withdraws consent in A only; B still has it, and B's read never touched a cache.
    _in(a, treated, lambda ctx: record_stop(treated, "web_chat"))
    assert _in(a, treated, lambda ctx: _consent_ok(ctx, treated)) is False
    assert _in(b, treated, lambda ctx: _consent_ok(ctx, treated)) is True
    assert _in(a, treated, lambda ctx: get_customer_context(treated))["pending_offers"] == []


def test_a_visitors_order_moves_their_stock_reads_off_the_cache(data_dir, tmp_path, mirrored):
    a = OverlayStore(data_dir, tmp_path / "sandbox" / "visitor-ordered")
    a.append("order_lines", [{"tenant_id": "kutumb-mart", "order_id": "ORD-T", "line_no": 0, "customer_id": "CUST-MEENA", "node_id": "DS-07", "sku": "SKU-MASALA-CHIPS-200G", "qty": 1, "price": 40.0, "discount": 0.0, "play_id": None, "ts": NOW_ISO}])
    _in(a, "CUST-MEENA", lambda ctx: _stock_info(ctx, "SKU-MASALA-CHIPS-200G", "DS-07"))
    s = fc.STATS.snapshot()
    assert s.get("overlay") == 1 and s.get("hit", 0) == 0
