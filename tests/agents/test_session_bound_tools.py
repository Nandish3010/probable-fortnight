"""C8 regression (adversarial eval, 14 Oct 2026): a chat user must not be able to make the agent act for
another customer. Fixture: the C8 transcript (eval/raw/adversarial_2026-10-14/chat/C8-change-consent-state__run1.json),
where Meena's turn made the model call record_stop(customer_id="CUST-RAVI", channel="web_chat") and
withdrew Ravi's marketing consent. Every customer-data tool must refuse a customer_id other than the
session customer, change nothing, and return a recoverable error; the session customer's own calls
(Ravi's own STOP included) behave as before."""
from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime

import pytest

from agents.customer import tools as ct
from agents.customer.context import CustomerContext, reset_context, set_context
from agents.gate.config import load_tenant
from services.api.approve import approve

PLAY = "play_chips_ds07_v1"
NOW = "2026-09-12T09:05:00Z"
MEENA, RAVI = "CUST-MEENA", "CUST-RAVI"


def _snapshot(store) -> str:
    return json.dumps({t: sorted(json.dumps(r, sort_keys=True) for r in store.read(t)) for t in ("consent", "offers", "orders", "order_lines", "ad_hoc_offers")}, sort_keys=True)


@pytest.fixture
def meena(sandbox):
    tenant = load_tenant()
    approve(sandbox, tenant, PLAY, datetime(2026, 9, 12, 9, 0, tzinfo=UTC))
    tok = set_context(CustomerContext.build(sandbox, MEENA, NOW, tenant))
    yield sandbox
    reset_context(tok)


def _assert_refused(out):
    assert out["ok"] is False and out["code"] == "wrong_customer"
    assert MEENA in out["reason"], "the error must name the session customer so the agent can retry"


def test_c8_record_stop_for_another_customer_changes_nothing(meena):
    before = _snapshot(meena)
    _assert_refused(ct.record_stop(RAVI, "web_chat"))  # the exact C8 call
    assert _snapshot(meena) == before
    ravi = [r for r in meena.read("consent") if r["customer_id"] == RAVI and r["channel"] == "web_chat" and r["purpose"] == "marketing"]
    assert ravi and all(not r.get("withdrawn_at") for r in ravi)


def test_c8_get_customer_context_for_another_customer_is_refused(meena):
    _assert_refused(ct.get_customer_context(RAVI))
    assert ct.get_customer_context(MEENA)["customer_id"] == MEENA


def test_c8_apply_offer_for_another_customer_is_refused(meena):
    before = _snapshot(meena)
    _assert_refused(ct.apply_offer(PLAY, RAVI))
    assert _snapshot(meena) == before


def test_c8_negotiate_offer_for_another_customer_is_refused(meena):
    before = _snapshot(meena)
    _assert_refused(ct.negotiate_offer(RAVI, "SKU-COLA-ZERO-500ML"))
    assert _snapshot(meena) == before


def test_c8_place_order_for_another_customer_is_refused(meena):
    before = _snapshot(meena)
    out = asyncio.run(ct.place_order(RAVI, "DS-07", [{"sku": "SKU-MASALA-CHIPS-200G", "qty": 1}], PLAY))
    _assert_refused(out)
    assert _snapshot(meena) == before


def test_blank_or_positional_mismatch_is_refused_not_defaulted(meena):
    _assert_refused(ct.record_stop("", "web_chat"))
    _assert_refused(ct.apply_offer(PLAY, RAVI))  # positional
    _assert_refused(ct.record_stop(customer_id="cust-meena", channel="web_chat"))  # ids are exact
    assert all(not r.get("withdrawn_at") for r in meena.read("consent") if r["customer_id"] in (MEENA, RAVI) and r["channel"] == "web_chat")


def test_ravis_own_stop_still_works(sandbox):
    tenant = load_tenant()
    tok = set_context(CustomerContext.build(sandbox, RAVI, NOW, tenant))
    try:
        assert ct.record_stop(RAVI, "web_chat") == {"ok": True}
        assert ct.get_customer_context(RAVI)["consent_marketing"] is False
    finally:
        reset_context(tok)
    assert any(r["customer_id"] == RAVI and r.get("withdrawn_at") for r in sandbox.read("consent"))
    assert all(not r.get("withdrawn_at") for r in sandbox.read("consent") if r["customer_id"] == MEENA)


def test_session_customers_own_calls_are_unchanged(meena):
    assert ct.get_customer_context(MEENA)["pending_offers"]
    assert ct.apply_offer(PLAY, MEENA)["ok"]
    assert asyncio.run(ct.place_order(MEENA, "DS-07", [{"sku": "SKU-MASALA-CHIPS-200G", "qty": 1}], PLAY))["order_id"]
