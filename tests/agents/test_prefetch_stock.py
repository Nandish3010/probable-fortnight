"""A stock question about an SKU in the customer's pending offer needs no get_stock round trip: the
stock is looked up in code and folded into the turn's plain-prose note (agents/customer/chat.py,
tools.prefetched_stock_note). Uses a scripted model on the vertex code path (the note is only built
there) that answers exactly as the stub would. It proves the plumbing and that the reply content is
identical with and without the tool call; whether the live model obeys the note is measured in
eval/raw/customer_latency_*_before_after/."""
import asyncio
import json
import re
from datetime import UTC, datetime
from typing import Any

import pytest
from google.adk.models import BaseLlm, LlmRequest, LlmResponse
from google.genai import types

import agents.customer.chat as chat_mod
from agents.customer.chat import reset_sessions, run_chat_async
from agents.customer.context import CustomerContext, reset_context, set_context
from agents.customer.stub_llm import LABELS, STRINGS, _fmt_date
from agents.customer.tools import get_customer_context, prefetched_stock_note
from agents.gate.config import load_tenant
from services.api.approve import approve

NOW = "2026-09-12T09:05:00Z"
ASK = "Is Darjeeling Tea in stock?"


class NoteAwareLlm(BaseLlm):
    """Answers a stock question from the note when it carries the stock, else calls get_stock."""

    model: str = "scripted-note-aware"
    sku: str = ""  # the offered sku it asks get_stock for when the note carries no stock

    @classmethod
    def supported_models(cls) -> list[str]:
        return [r"scripted-note-aware"]

    async def generate_content_async(self, llm_request: LlmRequest, stream: bool = False):
        text, responses = "", {}
        for c in llm_request.contents:
            for p in c.parts or []:
                if p.text and c.role == "user":
                    text, responses = p.text, {}
                if p.function_response:
                    responses[p.function_response.name] = dict(p.function_response.response or {})
        sku = re.search(r"\(sku ([A-Za-z0-9_-]+)\)", text)
        if "get_stock" in responses:
            st = responses["get_stock"]
        elif sku and "get_stock is not needed" in text:
            note = text.split("get_stock is not needed", 1)[1]
            st = {"sku": sku.group(1), "name": note.split(" (sku", 1)[0].split(": ", 1)[1], "availability": "few_left" if "only a few left" in note else "in_stock", "expiry_date": (re.search(r"best before (\d{4}-\d{2}-\d{2})", note) or [None, None])[1], "batch_id": re.search(r"stock ref (\S+?)\)?$", note.strip()).group(1)}
        else:
            part = types.Part(function_call=types.FunctionCall(name="get_stock", args={"sku": self.sku, "node_id": "DS-04"}))
            yield LlmResponse(content=types.Content(role="model", parts=[part]))
            return
        low = STRINGS["en"]["low_stock"] if st["availability"] == "few_left" else ""
        body = {"text": STRINGS["en"]["in_stock"].format(name=st["name"], low=low, bb=_fmt_date(st.get("expiry_date"))), "buttons": [{"id": f"add:{st['sku']}", "label": LABELS["en"]["add"]}, {"id": "no", "label": LABELS["en"]["no"]}], "citations": [{"type": "stock", "ref": st["batch_id"]}]}
        yield LlmResponse(content=types.Content(role="model", parts=[types.Part(text=json.dumps(body))]))


def _offered_sku(sandbox) -> str:
    return get_customer_context_for(sandbox, "CUST-RAVI")["pending_offers"][0]["sku"]


def get_customer_context_for(store, customer_id: str) -> dict[str, Any]:
    ctx = CustomerContext.build(store, customer_id, NOW, load_tenant())
    token = set_context(ctx)
    try:
        return get_customer_context(customer_id)
    finally:
        reset_context(token)


@pytest.fixture
def tea_offer(sandbox, monkeypatch):
    reset_sessions()
    approve(sandbox, load_tenant(), "play_tea_ds04_v1", datetime(2026, 9, 12, 9, 0, tzinfo=UTC))
    sku = _offered_sku(sandbox)

    monkeypatch.setattr("agents.customer.agent.vertex_model", lambda models: NoteAwareLlm(sku=sku))
    yield sandbox, sku
    reset_sessions()


def _turn(store, text):
    return asyncio.run(run_chat_async(store, "CUST-RAVI:web", text, backend="vertex", now_iso=NOW))[0]


def _names(env):
    return [t["name"] for t in env["tool_calls"] if "args" in t]


def test_offered_sku_stock_question_needs_no_get_stock_and_answer_is_unchanged(tea_offer, monkeypatch):
    store, sku = tea_offer
    after = _turn(store, ASK)
    assert "get_stock" not in _names(after)
    reset_sessions()
    monkeypatch.setattr(chat_mod, "prefetched_stock_note", lambda context, text: "")  # the old path: no note
    before = _turn(store, ASK)
    assert "get_stock" in _names(before)
    for key in ("text", "buttons", "citations"):
        assert after.get(key) == before.get(key), key


def test_note_gives_availability_band_never_a_count(tea_offer):
    store, sku = tea_offer
    ctx = CustomerContext.build(store, "CUST-RAVI", NOW, load_tenant())
    token = set_context(ctx)
    try:
        cc = get_customer_context("CUST-RAVI")
        note = prefetched_stock_note(cc, ASK)
        assert f"(sku {sku})" in note and ("in stock" in note or "only a few left" in note)
        assert not re.search(r"\b\d+ (units|pcs|pieces|left)\b", note) and "qty" not in note
        assert prefetched_stock_note(cc, "Any offers today?") == ""  # not a stock question
        assert prefetched_stock_note(cc, "do you have quinoa?") == ""  # another SKU: get_stock stays the tool
        assert prefetched_stock_note({**cc, "pending_offers": []}, ASK) == ""  # no offer, nothing to prefetch
    finally:
        reset_context(token)


def test_out_of_stock_offered_sku_is_not_prefetched(tea_offer, monkeypatch):
    store, sku = tea_offer
    ctx = CustomerContext.build(store, "CUST-RAVI", NOW, load_tenant())
    token = set_context(ctx)
    try:
        cc = get_customer_context("CUST-RAVI")
        import agents.customer.tools as tools

        orig = tools._stock_info
        monkeypatch.setattr(tools, "_stock_info", lambda c, k, n: {**orig(c, k, n), "qty": 0})
        assert prefetched_stock_note(cc, ASK) == ""  # get_stock still runs: demand signal + substitutes
    finally:
        reset_context(token)
