"""Accepting an offer must place exactly what was offered, at the offered price, and the receipt is
composed from the order record. Regression: an `add:<sku>` click on the Masala Chips + Coconut Water
bundle (Rs 61) was confirmed as "total is Rs 30" (the clicked sku alone, at list)."""
import asyncio
from datetime import UTC, datetime

import pytest

from agents.customer.chat import reset_sessions, run_chat_async
from agents.customer.context import CustomerContext, reset_context, set_context
from agents.customer.stub_llm import StubCustomerLlm
from agents.customer.tools import place_order
from agents.gate.config import load_tenant
from services.api.approve import approve

PLAY = "play_chips_ds07_v1"
CHIPS, COCONUT = "SKU-MASALA-CHIPS-200G", "SKU-COCONUT-WATER-1L"
NOW = "2026-09-12T09:05:00Z"


@pytest.fixture
def treated(sandbox):
    reset_sessions()
    approve(sandbox, load_tenant(), PLAY, datetime(2026, 9, 12, 9, 0, tzinfo=UTC))
    lang = {c["customer_id"]: c.get("language") for c in sandbox.read("customers")}
    cid = next(a["customer_id"] for a in sandbox.read("play_assignments") if a["play_id"] == PLAY and a["arm"] == "treated" and lang.get(a["customer_id"]) == "en")
    offered = next(o for o in sandbox.read("offers") if o["customer_id"] == cid and o["play_id"] == PLAY)["mechanic_params"]["bundle_price"]
    return cid, float(offered)


def _order(sandbox, cid):
    orders = [o for o in sandbox.read("orders") if o["customer_id"] == cid and o["ts"] == NOW]
    assert len(orders) == 1
    lines = [ln for ln in sandbox.read("order_lines") if ln["order_id"] == orders[0]["order_id"]]
    return orders[0], lines


def test_accepting_bundle_offer_orders_both_items_at_offered_price(sandbox, treated):
    cid, offered = treated
    env = asyncio.run(run_chat_async(sandbox, f"{cid}:web", f"add:{CHIPS}", now_iso=NOW))[0]
    order, lines = _order(sandbox, cid)
    assert sorted(ln["sku"] for ln in lines) == sorted([CHIPS, COCONUT])
    assert order["total_inr"] == offered == 61.0
    assert all(ln["play_id"] == PLAY for ln in lines)
    assert order["order_id"] in env["text"] and "61" in env["text"] and "Masala Chips" in env["text"] and "Coconut Water" in env["text"]


@pytest.mark.parametrize("play_id", ["", "PLAY-SKU-MASALA-CHIPS-200G", PLAY])
def test_model_sent_lines_and_play_id_do_not_change_the_order(sandbox, treated, play_id):
    """What the live model did: only the clicked sku, and an empty or invented play_id."""
    cid, offered = treated
    token = set_context(CustomerContext.build(sandbox, cid, NOW))
    try:
        out = asyncio.run(place_order(cid, "DS-07", [{"sku": CHIPS, "qty": 1}], play_id))
    finally:
        reset_context(token)
    assert sorted(ln["sku"] for ln in out["lines"]) == sorted([CHIPS, COCONUT])
    assert out["total_inr"] == offered
    assert f"{out['total_inr']:g}" in out["reply"] and out["order_id"] in out["reply"]
    _, lines = _order(sandbox, cid)
    assert {ln["play_id"] for ln in lines} == {PLAY}
    assert all(o.get("redeemed_at") for o in sandbox.read("offers") if o["customer_id"] == cid and o["play_id"] == PLAY)


def test_receipt_is_the_order_record_not_the_models_text(sandbox, treated, monkeypatch):
    cid, offered = treated
    orig = StubCustomerLlm._say
    monkeypatch.setattr(StubCustomerLlm, "_say", lambda self, p: orig(self, {**p, "text": "Your order is placed and the total is Rs 30."}))
    env = asyncio.run(run_chat_async(sandbox, f"{cid}:web", f"add:{CHIPS}", now_iso=NOW))[0]
    assert "Rs 30" not in env["text"] and "61" in env["text"]
    assert next(m for m in sandbox.read("messages") if m["message_id"] == env["message_id"])["text"] == env["text"]


@pytest.mark.parametrize("lang, marker", [("en", "Your order for"), ("kn", "ಆರ್ಡರ್")])
def test_receipt_language_is_the_turns_language(sandbox, treated, lang, marker):
    cid, offered = treated
    ctx = CustomerContext.build(sandbox, cid, NOW)
    ctx.reply_lang = lang
    token = set_context(ctx)
    try:
        out = asyncio.run(place_order(cid, "DS-07", [{"sku": CHIPS, "qty": 1}], PLAY))
    finally:
        reset_context(token)
    assert marker in out["reply"] and f"{offered:g}" in out["reply"]


def _orders(sandbox, cid):
    return [o for o in sandbox.read("orders") if o["customer_id"] == cid and o["ts"] == NOW]


def _place(sandbox, cid, play_id, sku=CHIPS, lang=""):
    ctx = CustomerContext.build(sandbox, cid, NOW)
    ctx.reply_lang = lang
    token = set_context(ctx)
    try:
        return asyncio.run(place_order(cid, "DS-07", [{"sku": sku, "qty": 1}], play_id))
    finally:
        reset_context(token)


def test_second_add_after_redemption_is_refused_not_a_list_price_order(sandbox, treated):
    cid, offered = treated
    first = asyncio.run(run_chat_async(sandbox, f"{cid}:web", f"add:{CHIPS}", now_iso=NOW))[0]
    assert "61" in first["text"] and len(_orders(sandbox, cid)) == 1
    second = asyncio.run(run_chat_async(sandbox, f"{cid}:web", f"add:{CHIPS}", now_iso=NOW))[0]
    assert second["text"] == "This offer has already been used on your account."
    assert len(_orders(sandbox, cid)) == 1 and "ORD-" not in second["text"] and "total" not in second["text"]


def test_refusal_text_comes_from_code_not_the_model(sandbox, treated, monkeypatch):
    cid, _ = treated
    asyncio.run(run_chat_async(sandbox, f"{cid}:web", f"add:{CHIPS}", now_iso=NOW))
    orig = StubCustomerLlm._say
    monkeypatch.setattr(StubCustomerLlm, "_say", lambda self, p: orig(self, {**p, "text": "Sure! Your order is placed at Rs 30."}))
    env = asyncio.run(run_chat_async(sandbox, f"{cid}:web", f"add:{CHIPS}", now_iso=NOW))[0]
    assert env["text"] == "This offer has already been used on your account." and len(_orders(sandbox, cid)) == 1


def test_refusal_is_in_the_turn_language(sandbox, treated):
    cid, _ = treated
    assert _place(sandbox, cid, PLAY)["order_id"]
    kn = _place(sandbox, cid, PLAY, lang="kn")
    assert kn["refused"] == "already_redeemed" and "ಈಗಾಗಲೇ" in kn["reply"] and not kn["order_id"]


def test_consent_withdrawn_customer_is_refused(sandbox, treated):
    cid, _ = treated
    rows = sandbox.read("consent")
    for r in rows:
        if r["customer_id"] == cid and r["purpose"] == "marketing":
            r["withdrawn_at"] = NOW
    sandbox.write("consent", rows)
    env = asyncio.run(run_chat_async(sandbox, f"{cid}:web", f"add:{CHIPS}", now_iso=NOW))[0]
    assert "opted out" in env["text"] and not _orders(sandbox, cid)


def test_control_arm_customer_naming_the_play_is_refused(sandbox, treated):
    holdout = next(a["customer_id"] for a in sandbox.read("play_assignments") if a["play_id"] == PLAY and a["arm"] == "holdout")
    out = _place(sandbox, holdout, PLAY, lang="en")
    assert out["refused"] == "not_treated" and "not available" in out["reply"]
    assert not _orders(sandbox, holdout)


def test_orders_with_no_offer_context_are_plain_and_leave_the_offer_alone(sandbox, treated):
    cid, _ = treated
    tea = "SKU-DARJEELING-TEA-100G"
    out = _place(sandbox, cid, "PLAY-INVENTED", sku=tea)
    _, lines = _order(sandbox, cid)
    assert out["order_id"] and [ln["sku"] for ln in lines] == [tea] and not lines[0].get("play_id") and float(lines[0]["discount"]) == 0.0
    assert not any(o.get("redeemed_at") for o in sandbox.read("offers") if o["customer_id"] == cid and o["play_id"] == PLAY)
