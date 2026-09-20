"""Run one stylist turn and return chat envelopes (docs/schemas/chat_envelope.schema.json).

A garment photo or a selfie is read into attributes before the agent runs (agents/stylist/vision.py)
and folded into the turn's text, so the model and the stub cascade see one input shape whether the
customer typed or uploaded. Sessions live under their own ADK app_name so they never collide with
the grocery agent's sessions for the same customer_id.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from agents.chat_runtime import ChatRuntime
from agents.gate.config import load_tenant
from agents.gate.store import LocalStore

from .agent import build_stylist_agent
from .context import StylistContext, reset_context, set_context
from .vision import describe_garment_photo, read_skin_tone

APP = "taal_stylist"
RUNTIME = ChatRuntime(APP, "stylist", lambda store, backend: build_stylist_agent({p["sku"]: p for p in store.read("apparel_products")}, backend))


def _compose_photo_turn(text: str, image_kind: str, image_data_url: str | None, photo_ref: str | None, backend: str | None) -> tuple[str, list[dict[str, Any]]]:
    if image_kind == "selfie":
        read = read_skin_tone(image_data_url=image_data_url, photo_ref=photo_ref, backend=backend)
        if read["undertone"] and read["depth"]:
            suffix = f"(selfie: {read['undertone']} undertone, {read['depth']} depth, confidence {read['confidence']:.2f})"
        else:
            suffix = "(selfie: unclear)"
        base = text or "my skin tone"
        extra = [{"name": "read_skin_tone", "args": {"photo_ref": read["photo_ref"], "confidence": read["confidence"]}}]
        return f"{base} {suffix}", extra
    read = describe_garment_photo(image_data_url=image_data_url, photo_ref=photo_ref, backend=backend)
    note = ", not sure" if read["needs_confirmation"] else ""
    base = text or "What goes with this?"
    extra = [{"name": "describe_garment_photo", "args": {"photo_ref": read["photo_ref"], "confidence": read["confidence"]}}]
    return f"{base} (photo: {read['description']}{note})", extra


async def run_stylist_chat_async(store: LocalStore, session_id: str, text: str, customer_id: str | None = None, backend: str | None = None, now_iso: str | None = None, image_data_url: str | None = None, photo_ref: str | None = None, image_kind: str = "garment") -> list[dict[str, Any]]:
    from agents.chat_runtime import now_iso as _now_iso

    customer_id = customer_id or session_id.split(":", 1)[0]
    channel = "web_chat" if session_id.endswith(":web") else "whatsapp"
    now = now_iso or _now_iso()
    tenant = load_tenant()
    ctx = StylistContext.build(store, customer_id, now, tenant, channel)
    token = set_context(ctx)
    try:
        extra_tool_calls: list[dict[str, Any]] = []
        turn_text = text
        if image_data_url or photo_ref:
            turn_text, extra_tool_calls = _compose_photo_turn(text, image_kind, image_data_url, photo_ref, backend)
        cust = store.find("customers", customer_id=customer_id)
        language = (cust[-1].get("language", "en") if cust else "en") or "en"
        envelope = await RUNTIME.run_turn(store, session_id, turn_text, customer_id, backend, now, tenant, channel, language, extra_tool_calls=extra_tool_calls)
        return [envelope]
    finally:
        reset_context(token)


def run_stylist_chat(data_dir: str | Path | LocalStore, session_id: str, text: str, customer_id: str | None = None, **kw: Any) -> list[dict[str, Any]]:
    store = data_dir if isinstance(data_dir, LocalStore) else LocalStore(data_dir)
    return asyncio.run(run_stylist_chat_async(store, session_id, text, customer_id, **kw))


def reset_sessions() -> None:
    RUNTIME.reset()


__all__ = ["APP", "RUNTIME", "reset_sessions", "run_stylist_chat", "run_stylist_chat_async"]
