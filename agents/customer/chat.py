"""Run one customer turn and return chat envelopes (docs/schemas/chat_envelope.schema.json).

Sessions: one ADK session per `customer_id:web`, kept in an InMemorySessionService per store root
(VertexAiSessionService in production). Messages are persisted to conversations / messages by the
shared runtime in agents/chat_runtime.py.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from agents.chat_runtime import ENVELOPE_SCHEMA, ChatRuntime, clamp, now_iso, parse_envelope
from agents.gate.config import load_tenant
from agents.gate.store import LocalStore

from .agent import build_customer_agent
from .context import CustomerContext, reset_context, set_context

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
        envelope = await RUNTIME.run_turn(store, session_id, text, customer_id, backend, now, tenant, channel, language)
        return [envelope]
    finally:
        reset_context(token)


def run_chat(data_dir: str | Path | LocalStore, session_id: str, text: str, customer_id: str | None = None, **kw: Any) -> list[dict[str, Any]]:
    store = data_dir if isinstance(data_dir, LocalStore) else LocalStore(data_dir)
    return asyncio.run(run_chat_async(store, session_id, text, customer_id, **kw))


def reset_sessions() -> None:
    RUNTIME.reset()


__all__ = ["APP", "ENVELOPE_SCHEMA", "RUNTIME", "reset_sessions", "run_chat", "run_chat_async"]
