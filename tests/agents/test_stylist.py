"""The scripted conversations under fixtures/conversations_stylist run against the stub Stylist
Agent in a sandbox, the same pattern as tests/agents/test_customer.py for the grocery agent."""
import json
from datetime import UTC, datetime
from pathlib import Path

import jsonschema
import pytest

from agents.chat_runtime import ENVELOPE_SCHEMA
from agents.customer.chat import reset_sessions as reset_customer_sessions
from agents.customer.chat import run_chat_async
from agents.stylist.chat import reset_sessions as reset_stylist_sessions
from agents.stylist.chat import run_stylist_chat_async

ROOT = Path(__file__).resolve().parents[2]
CONVOS = sorted((ROOT / "fixtures" / "conversations_stylist").glob("*.json"))
NOW = datetime(2026, 9, 12, 9, 0, tzinfo=UTC).isoformat().replace("+00:00", "Z")


@pytest.mark.parametrize("path", CONVOS, ids=[p.stem for p in CONVOS])
def test_conversation(path: Path, sandbox):
    convo = json.loads(path.read_text(encoding="utf-8"))
    reset_stylist_sessions()
    cid = convo["customer_id"]
    session = f"{cid}:web"
    for turn in convo["turns"]:
        kwargs = {}
        if turn.get("photo_ref"):
            kwargs["photo_ref"] = turn["photo_ref"]
        if turn.get("image_kind"):
            kwargs["image_kind"] = turn["image_kind"]
        env = _run(sandbox, session, turn.get("text", ""), **kwargs)
        jsonschema.validate(env, ENVELOPE_SCHEMA, format_checker=jsonschema.FormatChecker())
        exp = turn["expect"]
        called = [t["name"] for t in env["tool_calls"] if "args" in t]
        text = env["text"]
        if "contains_any" in exp:
            assert any(s in text for s in exp["contains_any"]), (text, exp["contains_any"])
        for s in exp.get("not_contains", []):
            assert s not in text, text
        for t in exp.get("tool_called", []):
            assert t in called, (t, called)
        for t in exp.get("tool_not_called", []):
            assert t not in called, (t, called)
        if exp.get("buttons_min"):
            assert len(env.get("buttons") or []) >= exp["buttons_min"]
        if exp.get("buttons_max"):
            assert len(env.get("buttons") or []) <= exp["buttons_max"]
        if exp.get("list_rows_min"):
            assert len((env.get("list") or {}).get("rows") or []) >= exp["list_rows_min"], env.get("list")
        if exp.get("list_rows_max"):
            assert len((env.get("list") or {}).get("rows") or []) <= exp["list_rows_max"]
        if exp.get("citation_type"):
            assert any(c["type"] == exp["citation_type"] for c in env.get("citations") or []), env.get("citations")
        if "style_ask_recorded" in exp:
            rows = [r for r in sandbox.read("style_requests") if r["customer_id"] == cid]
            assert rows, "expected a style_requests row to be written"
            last = rows[-1]
            for k, v in exp["style_ask_recorded"].items():
                assert last.get(k) == v, (k, last.get(k), v, last)


def _run(sandbox, session_id: str, text: str, **kw):
    import asyncio

    return asyncio.run(run_stylist_chat_async(sandbox, session_id, text, now_iso=NOW, **kw))[0]


def test_fourteen_conversations_exist():
    assert len(CONVOS) >= 10


def test_stylist_sessions_do_not_collide_with_grocery_sessions(sandbox):
    """The same customer_id:web session id runs on two different ADK apps (taal_customer,
    taal_stylist); a stylist turn's tool calls must never include a grocery tool and vice versa."""
    import asyncio

    reset_customer_sessions()
    reset_stylist_sessions()
    session = "CUST-MEENA:web"
    grocery_env = asyncio.run(run_chat_async(sandbox, session, "Do you have Cola Zero?", now_iso=NOW))[0]
    stylist_env = asyncio.run(run_stylist_chat_async(sandbox, session, "What goes with a mustard kurta?", now_iso=NOW))[0]
    grocery_tools = {t["name"] for t in grocery_env["tool_calls"]}
    stylist_tools = {t["name"] for t in stylist_env["tool_calls"]}
    assert grocery_tools.isdisjoint({"suggest_pairings", "find_apparel", "get_style_context", "describe_item"})
    assert stylist_tools.isdisjoint({"get_stock", "list_products", "get_customer_context", "apply_offer"})


def test_every_ask_is_recorded_deterministically(sandbox):
    """A miss and a hit each write exactly one style_requests row with the right `fulfilled`."""
    import asyncio

    reset_stylist_sessions()
    session = "CUST-RAVI:web"
    asyncio.run(run_stylist_chat_async(sandbox, session, "What goes with a mustard yellow kurta?", now_iso=NOW))
    from agents.stylist.context import StylistContext, reset_context, set_context
    from agents.stylist.tools import find_apparel

    ctx = StylistContext.build(sandbox, "CUST-RAVI", NOW, sandbox and __import__("agents.gate.config", fromlist=["load_tenant"]).load_tenant())
    token = set_context(ctx)
    try:
        find_apparel("query for apparel nowhere on the shelf at an outlet", "OUT-01")
    finally:
        reset_context(token)
    rows = sandbox.read("style_requests")
    assert any(r["source"] == "suggest_pairings" and r["fulfilled"] for r in rows)
    assert any(r["source"] == "find_apparel" and not r["fulfilled"] for r in rows)
