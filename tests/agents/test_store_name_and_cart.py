"""A customer is shown a store's name ("Dark store 04"), never its node id ("DS-04"), and no reply
says an item is in a cart or order before one was placed. The id reaches the model only as the
node_id for stock tools; this covers the note it is given, the guard on the reply (English and
Kannada), and the stub chat path for Ravi after the Tea Approve."""
import asyncio
import re
from datetime import UTC, datetime

from agents.chat_runtime import name_nodes
from agents.customer.chat import reset_sessions, run_chat_async
from agents.customer.tools import context_summary
from agents.gate.config import load_tenant
from services.api.approve import approve

NODES = [
    {"node_id": "DS-04", "name": "Dark store 04 (North Bengaluru)"},
    {"node_id": "OUT-02", "name": "Outlet 02 (South Bengaluru)"},
]
NODE_ID = re.compile(r"\b(?:DS|OUT)-\d{2}\b")
CART = re.compile(r"cart|your order|reservation|reserved for you|we saved|ಕಾರ್ಟ", re.IGNORECASE)
NOW = "2026-09-12T09:05:00Z"


def test_context_note_leads_with_the_store_name_and_marks_the_id_tool_only():
    note = context_summary({"home_node_id": "DS-04", "home_node_name": "Dark store 04", "language": "en", "consent_marketing": False, "pending_offers": [], "memory": []})
    assert note.startswith("home store Dark store 04 ")
    assert "never say it to the customer" in note


def test_a_reply_that_echoes_a_node_id_is_rewritten_with_the_store_name():
    assert name_nodes("Darjeeling Tea 100G is in stock at DS-04. Add it?", NODES) == "Darjeeling Tea 100G is in stock at Dark store 04. Add it?"
    assert name_nodes("ಚಹಾ DS-04 ನಲ್ಲಿ ಲಭ್ಯ, OUT-02 ನಲ್ಲಿಯೂ.", NODES) == "ಚಹಾ Dark store 04 ನಲ್ಲಿ ಲಭ್ಯ, Outlet 02 ನಲ್ಲಿಯೂ."
    assert name_nodes("At DS-99", NODES) == "At your store"  # unknown id: never shown raw
    assert name_nodes("No ids here", NODES) == "No ids here"


def test_ravi_stock_answer_and_first_offer_reply_show_no_node_id_and_no_cart_wording(sandbox):
    reset_sessions()
    approve(sandbox, load_tenant(), "play_tea_ds04_v1", datetime(2026, 9, 12, 9, 0, tzinfo=UTC))
    session = "CUST-RAVI:web"
    offer = asyncio.run(run_chat_async(sandbox, session, "Any offers today?", now_iso=NOW))[0]
    stock = asyncio.run(run_chat_async(sandbox, session, "Is Darjeeling Tea in stock?", now_iso=NOW))[0]
    for env in (offer, stock):
        assert not NODE_ID.search(env["text"]), env["text"]
        assert not CART.search(env["text"]), env["text"]
