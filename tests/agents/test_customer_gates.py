"""Customer-tool gates that are code, not model judgement. The consent gate: once consent is withdrawn, every offer path in the
Customer tools refuses on its own, with no model turn in the loop. (Whether a free-text "STOP"
reaches `record_stop` is the model's call in vertex mode -- agents/customer/prompts/customer.md --
and is covered by the scripted conversations 10-12, not here.)"""
from __future__ import annotations

from datetime import UTC, datetime

from agents.customer import tools as ct
from agents.customer.context import CustomerContext, reset_context, set_context
from agents.gate.config import load_tenant
from services.api.approve import approve


def test_withdrawn_consent_blocks_every_offer_path_without_a_model(sandbox):
    tenant = load_tenant()
    play_id = "play_chips_ds07_v1"
    approve(sandbox, tenant, play_id, datetime(2026, 9, 12, 9, 0, tzinfo=UTC))
    tok = set_context(CustomerContext.build(sandbox, "CUST-MEENA", "2026-09-12T09:05:00Z", tenant))
    try:
        before = ct.get_customer_context("CUST-MEENA")
        assert before["consent_marketing"] and before["pending_offers"], "fixture drifted: Meena should hold a live chips offer"
        assert ct.apply_offer(play_id, "CUST-MEENA")["ok"]

        assert ct.record_stop("CUST-MEENA", "web_chat") == {"ok": True}

        after = ct.get_customer_context("CUST-MEENA")
        assert after["consent_marketing"] is False and after["pending_offers"] == []
        assert ct.apply_offer(play_id, "CUST-MEENA") == {"ok": False, "reason": "no marketing consent on this channel"}
        assert ct.negotiate_offer("CUST-MEENA", "SKU-COLA-ZERO-500ML") == {"ok": False, "reason": "no marketing consent on this channel"}
        assert not [o for o in sandbox.read("offers") if o["customer_id"] == "CUST-MEENA"]
    finally:
        reset_context(tok)


def test_ad_hoc_discount_never_exceeds_the_tenant_ceiling_or_the_margin_floor(sandbox):
    """negotiate_offer is the one discount path with no approved play behind it. The model only
    phrases what it returns; the percentage comes from min(ad_hoc_max_discount_pct, margin
    headroom above the category floor) -- checked here for every sku in the catalogue."""
    tenant = load_tenant()
    ceiling_pct = float(tenant.thresholds["ad_hoc_max_discount_pct"])
    tok = set_context(CustomerContext.build(sandbox, "CUST-MEENA", "2026-09-12T09:05:00Z", tenant))
    try:
        offered = refused = 0
        for p in sandbox.read("products"):
            sandbox.write("ad_hoc_offers", [])  # isolate each sku from the shared frequency cap
            out = ct.negotiate_offer("CUST-MEENA", p["sku"])
            price, cost = float(p["list_price"]), float(p["unit_cost"])
            headroom = (price - cost) / price * 100.0 - float(p["margin_floor_pct"])
            if not out["ok"]:
                assert headroom <= 0 and "margin floor" in out["reason"], (p["sku"], out)
                refused += 1
                continue
            offered += 1
            assert 0 < out["discount_pct"] <= round(min(ceiling_pct, headroom), 1), (p["sku"], out, headroom)
            margin_after = (price * (1 - out["discount_pct"] / 100.0) - cost) / (price * (1 - out["discount_pct"] / 100.0)) * 100.0
            assert margin_after >= float(p["margin_floor_pct"]) - 0.5, (p["sku"], margin_after)
        assert offered > 0
    finally:
        reset_context(tok)
