"""Run one customer turn and return chat envelopes (docs/schemas/chat_envelope.schema.json).

Sessions: one ADK session per visitor and customer -- session id `<visitor>:<customer_id>:web`,
user id `<visitor>:<customer_id>` (agents/chat_runtime.py::adk_ids), where the visitor is the
X-Taal-Visitor sandbox id. The API-facing session id stays `customer_id:web`. Backend: an
InMemorySessionService per visitor sandbox (lost on restart) unless TAAL_SESSION_BACKEND=vertex,
which keeps sessions on a Vertex AI Agent Engine across restarts (verified in
eval/raw/vertex_sessions_2026-09-24; visitor-isolation fixes and offline measurements in
eval/raw/sessions_cache_2026-09-27). infra/deploy.sh sets that flag only when
ENABLE_VERTEX_SESSIONS=1, hard-coded to 0 at infra/deploy.sh:16, so it is off in the deployed
service. Stock and customer-profile reads may come from the Firestore serving cache
(TAAL_SERVING_CACHE=firestore, gated the same way by ENABLE_SERVING_CACHE, hard-coded to 0 at
infra/deploy.sh:22, so likewise off in the deployed service) only when safe for this visitor;
offers and consent always come from the visitor's own store. Messages are persisted to
conversations / messages by the shared runtime in agents/chat_runtime.py.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from agents.chat_runtime import (
    ENVELOPE_SCHEMA,
    ChatRuntime,
    clamp,
    detect_lang,
    now_iso,
    parse_envelope,
)
from agents.gate.config import load_models, load_tenant
from agents.gate.store import LocalStore

from .agent import build_customer_agent
from .context import CustomerContext, reset_context, set_context
from .tools import context_summary, get_customer_context, offer_summary_en

APP = "taal_customer"


def _offer_gloss(store: LocalStore, customer_id: str, env: dict[str, Any]) -> str | None:
    """The gloss template when a non-English reply carries no usable one: the offer the reply cites
    (a `play` citation), summarised in English from the offer's own structured fields."""
    plays = {c["ref"] for c in env.get("citations") or [] if c["type"] == "play"}
    offers = [o for o in store.read("offers") if o["customer_id"] == customer_id and o["play_id"] in plays]
    return offer_summary_en(offers[-1], {p["sku"]: p["name"] for p in store.read("products")}) if offers else None


RUNTIME = ChatRuntime(APP, "customer", lambda store, backend: build_customer_agent({p["name"].lower(): p["sku"] for p in store.read("products")}, backend), gloss_fallback=_offer_gloss)
_now = now_iso
_parse_envelope = parse_envelope
_clamp = clamp


async def run_chat_async(store: LocalStore, session_id: str, text: str, customer_id: str | None = None, backend: str | None = None, now_iso: str | None = None, visitor_id: str | None = None) -> list[dict[str, Any]]:
    customer_id = customer_id or session_id.split(":", 1)[0]
    channel = "web_chat" if session_id.endswith(":web") else "whatsapp"
    now = now_iso or _now()
    tenant = load_tenant()
    ctx = CustomerContext.build(store, customer_id, now, tenant, channel)
    token = set_context(ctx)
    try:
        language = (store.find("customers", customer_id=customer_id) or [{}])[-1].get("language", "en") or "en"
        ctx.reply_lang = detect_lang(text, language)
        # get_customer_context is a pure, deterministic store lookup (no model involved) that the
        # prompt asked the model to call as its very first tool on every turn -- meaning every
        # single-turn /chat call against the live model paid for two sequential Gemini round trips
        # (decide-to-call-the-tool, then produce the final reply) even when the model never needed
        # a second tool. Measured live (see eval/evaluation.md, "Customer Agent /chat p95 latency,
        # round two"): a bare "hi" or "any offers?" turn took ~4-6s for exactly two round trips of
        # ~2-3s each. Fetched here in Python instead and folded into the turn text as an already-done tool result,
        # so a turn that needs no other tool resolves in one round trip instead of two. Only done
        # on the vertex backend: the stub model parses the raw user text with regexes (agents/
        # customer/stub_llm.py) and has no use for -- and would be confused by -- the appended
        # note, and it never pays a real network round trip anyway.
        #
        # The first version of this fix appended the raw customer_context dict as JSON plus a
        # "never quote this" instruction, inline in the user turn's own text. Live-verified to
        # leak: a real reply on the deployed app echoed the entire bracketed block, JSON and all,
        # to the customer (see eval/evaluation.md's write-up of the incident). Asking a model not
        # to repeat a block of JSON syntax sitting right in front of it in its own turn is not a
        # reliable guardrail -- context_summary() renders the same facts as one line of plain
        # prose instead, so there is no JSON left to quote (a short parenthetical description,
        # never a raw dict).
        effective_backend = backend or load_models()["backend"]
        turn_text = text
        extra_tool_calls: list[dict[str, Any]] = []
        if effective_backend == "vertex":
            customer_context = get_customer_context(customer_id)
            # The language directive folded into the note below is turn-specific (detect_lang on
            # this message's own script), NOT the stored preference -- except on a proactive
            # first-turn delivery: the pending offer's text was already generated once, in the
            # customer's stored language, at /approve time (services/api/approve.py), and the
            # prompt says to deliver it word for word. Telling the model "reply in English" right
            # before "deliver this Kannada text verbatim" would fight itself, so this one case
            # keeps the stored-preference fallback (turn_language=None) instead of detecting from
            # `text`, which is usually a canned English trigger phrase ("Any offers today?") with
            # no bearing on the offer's own pre-set language.
            is_first_turn = not store.find("conversations", session_id=session_id)
            has_pending_offer = bool(customer_context.get("pending_offers"))
            turn_language = None if (is_first_turn and has_pending_offer) else detect_lang(text, language)
            turn_text = f"{text}\n\n(known: {context_summary(customer_context, turn_language=turn_language)})"
            extra_tool_calls = [{"name": "get_customer_context", "args": {"customer_id": customer_id}}]
        envelope = await RUNTIME.run_turn(store, session_id, turn_text, customer_id, backend, now, tenant, channel, language, extra_tool_calls=extra_tool_calls, visitor_id=visitor_id)
        return [envelope]
    finally:
        reset_context(token)


def run_chat(data_dir: str | Path | LocalStore, session_id: str, text: str, customer_id: str | None = None, **kw: Any) -> list[dict[str, Any]]:
    store = data_dir if isinstance(data_dir, LocalStore) else LocalStore(data_dir)
    return asyncio.run(run_chat_async(store, session_id, text, customer_id, **kw))


def reset_sessions(store: LocalStore | None = None) -> None:
    """Drop every visitor's runners, or only `store`'s."""
    RUNTIME.reset(store)


__all__ = ["APP", "ENVELOPE_SCHEMA", "RUNTIME", "reset_sessions", "run_chat", "run_chat_async"]
