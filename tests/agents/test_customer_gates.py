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
        refused = ct.apply_offer(play_id, "CUST-MEENA")
        assert (refused["ok"], refused["reason"], refused["code"]) == (False, "no marketing consent on this channel", "no_consent") and refused["reply"]
        assert ct.negotiate_offer("CUST-MEENA", "SKU-COLA-ZERO-500ML") == {"ok": False, "reason": "no marketing consent on this channel"}
        assert not [o for o in sandbox.read("offers") if o["customer_id"] == "CUST-MEENA"]
    finally:
        reset_context(tok)


def test_negotiate_offer_personalizes_volume_discount_to_the_customers_own_median(sandbox):
    """The behavioural personalization asked for directly: a volume_discount's min_qty is the
    customer's own median order size plus the configured nudge, not a flat number -- a customer
    who always buys 1 gets asked to buy a few more than that, and the reply cites the real median
    it was computed from (never a bare 'eligible')."""
    tenant = load_tenant()
    sandbox.write("order_lines", [
        {"tenant_id": "kutumb-mart", "order_id": f"ORD-TEST-{i}", "line_no": 1, "customer_id": "CUST-MEENA", "node_id": "DS-07", "sku": "SKU-COLA-ZERO-500ML", "qty": 1, "price": 58.5, "discount": 0.0, "play_id": None, "ts": f"2026-09-0{i}T10:00:00Z"}
        for i in range(1, 6)
    ])
    tok = set_context(CustomerContext.build(sandbox, "CUST-MEENA", "2026-09-12T09:05:00Z", tenant))
    try:
        out = ct.negotiate_offer("CUST-MEENA", "SKU-COLA-ZERO-500ML")
        assert out["ok"] and out["mechanic"] == "volume_discount"
        step = int(tenant.thresholds.get("ad_hoc_volume_nudge_step", 3))
        assert out["min_qty"] == 1 + step, out
        assert "1" in out["reason"] and str(out["min_qty"]) in out["reason"] and out["reason"] != "eligible"
    finally:
        reset_context(tok)


def test_negotiate_offer_declines_volume_discount_for_an_already_loyal_customer(sandbox):
    """The other half of the same ask: a customer whose own history already meets or beats the
    loyal-quantity threshold gets no volume_discount at all -- they were always going to buy that
    much, so a discount on it is pure margin given away, never an LLM call away from being offered
    anyway."""
    tenant = load_tenant()
    already_loyal = float(tenant.thresholds.get("ad_hoc_volume_already_loyal_qty", 4))
    sandbox.write("order_lines", [
        {"tenant_id": "kutumb-mart", "order_id": f"ORD-TEST-{i}", "line_no": 1, "customer_id": "CUST-RAVI", "node_id": "DS-07", "sku": "SKU-COLA-ZERO-500ML", "qty": int(already_loyal), "price": 58.5, "discount": 0.0, "play_id": None, "ts": f"2026-09-0{i}T10:00:00Z"}
        for i in range(1, 4)
    ])
    tok = set_context(CustomerContext.build(sandbox, "CUST-RAVI", "2026-09-12T09:05:00Z", tenant))
    try:
        out = ct.negotiate_offer("CUST-RAVI", "SKU-COLA-ZERO-500ML")
        assert out == {"ok": False, "reason": f"already orders about {already_loyal:g} units of this at a time on their own -- no incremental offer needed"}
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
