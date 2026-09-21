"""Run one customer turn and return chat envelopes (docs/schemas/chat_envelope.schema.json).

Sessions: one ADK session per `customer_id:web`, kept in an InMemorySessionService per store root
(VertexAiSessionService in production). Messages are persisted to conversations / messages by the
shared runtime in agents/chat_runtime.py.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from agents.chat_runtime import ENVELOPE_SCHEMA, ChatRuntime, clamp, now_iso, parse_envelope
from agents.gate.config import load_models, load_tenant
from agents.gate.store import LocalStore

from .agent import build_customer_agent
from .context import CustomerContext, reset_context, set_context
from .tools import get_customer_context

APP = "taal_customer"
RUNTIME = ChatRuntime(APP, "customer", lambda store, backend: build_customer_agent({p["name"].lower(): p["sku"] for p in store.read("products")}, backend))
_now = now_iso
_parse_envelope = parse_envelope
_clamp = clamp


async def run_chat_async(store: LocalStore, session_id: str, text: str, customer_id: str | None = None, backend: str | None = None, now_iso: str | None = None) -> list[dict[str, Any]]:
    customer_id = customer_id or session_id.split(":", 1)[0]
    channel = "web_chat" if session_id.endswith(":web") else "whatsapp"
    now = now_iso or _now()
    tenant = load_tenant()
    ctx = CustomerContext.build(store, customer_id, now, tenant, channel)
    token = set_context(ctx)
    try:
        language = (store.find("customers", customer_id=customer_id) or [{}])[-1].get("language", "en") or "en"
        # get_customer_context is a pure, deterministic store lookup (no model involved) that the
        # prompt asked the model to call as its very first tool on every turn -- meaning every
        # single-turn /chat call against the live model paid for two sequential Gemini round trips
        # (decide-to-call-the-tool, then produce the final reply) even when the model never needed
        # a second tool. Measured live (see eval/evaluation.md, "Customer Agent /chat p95 latency,
        # round two"): a bare "hi" or "any offers?" turn took ~4-6s for exactly two round trips of
        # ~2-3s each. Fetched here in Python instead (same pattern agents/stylist/chat.py already
        # uses for its vision reads) and folded into the turn text as an already-done tool result,
        # so a turn that needs no other tool resolves in one round trip instead of two. Only done
        # on the vertex backend: the stub model parses the raw user text with regexes (agents/
        # customer/stub_llm.py) and has no use for -- and would be confused by -- an appended JSON
        # blob, and it never pays a real network round trip anyway.
        effective_backend = backend or load_models()["backend"]
        turn_text = text
        extra_tool_calls: list[dict[str, Any]] = []
        if effective_backend == "vertex":
            customer_context = get_customer_context(customer_id)
            turn_text = (
                f"{text}\n\n"
                f"[INTERNAL, not part of what the customer said or should ever see verbatim: "
                f"get_customer_context has already run for you this turn -- do not call it again. "
                f"Use these facts to decide your reply, then write that reply as ordinary prose; "
                f"never quote this bracket, its field names, or its raw values.\n"
                f"get_customer_context_result = {json.dumps(customer_context, ensure_ascii=False)}]"
            )
            extra_tool_calls = [{"name": "get_customer_context", "args": {"customer_id": customer_id}}]
        envelope = await RUNTIME.run_turn(store, session_id, turn_text, customer_id, backend, now, tenant, channel, language, extra_tool_calls=extra_tool_calls)
        return [envelope]
    finally:
        reset_context(token)


def run_chat(data_dir: str | Path | LocalStore, session_id: str, text: str, customer_id: str | None = None, **kw: Any) -> list[dict[str, Any]]:
    store = data_dir if isinstance(data_dir, LocalStore) else LocalStore(data_dir)
    return asyncio.run(run_chat_async(store, session_id, text, customer_id, **kw))


def reset_sessions() -> None:
    RUNTIME.reset()


__all__ = ["APP", "ENVELOPE_SCHEMA", "RUNTIME", "reset_sessions", "run_chat", "run_chat_async"]
