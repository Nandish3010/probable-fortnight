"""Run one customer turn and return chat envelopes (docs/schemas/chat_envelope.schema.json).

Sessions: one ADK session per `customer_id:web`, kept in an InMemorySessionService per store root
(VertexAiSessionService in production). Messages are persisted to conversations / messages.
"""
from __future__ import annotations

import asyncio
import json
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import jsonschema
from google.adk.runners import InMemoryRunner
from google.genai import types

from agents.gate.config import ROOT, load_tenant
from agents.gate.store import LocalStore

from .agent import build_customer_agent
from .context import CustomerContext, reset_context, set_context

APP = "taal_customer"
ENVELOPE_SCHEMA = json.loads((ROOT / "docs" / "schemas" / "chat_envelope.schema.json").read_text(encoding="utf-8"))
_VALIDATOR = jsonschema.Draft202012Validator(ENVELOPE_SCHEMA, format_checker=jsonschema.FormatChecker())
_RUNNERS: dict[str, InMemoryRunner] = {}
_SESSION_LOCK = asyncio.Lock()


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _runner(store: LocalStore, backend: str | None) -> InMemoryRunner:
    key = f"{store.root}|{backend or ''}"
    if key not in _RUNNERS:
        catalog = {p["name"].lower(): p["sku"] for p in store.read("products")}
        _RUNNERS[key] = InMemoryRunner(agent=build_customer_agent(catalog, backend), app_name=APP)
    return _RUNNERS[key]


def _parse_envelope(text: str) -> dict[str, Any]:
    raw = text.strip()
    m = re.search(r"\{.*\}", raw, re.S)
    if m:
        try:
            obj = json.loads(m.group(0))
            if isinstance(obj, dict) and "text" in obj:
                return obj
        except json.JSONDecodeError:
            pass
    return {"text": raw[:4096]}


def _clamp(env: dict[str, Any]) -> dict[str, Any]:
    if env.get("buttons"):
        env["buttons"] = [{"id": str(b["id"])[:64], "label": str(b["label"])[:20]} for b in env["buttons"][:3]]
    if env.get("list"):
        rows = env["list"].get("rows") or []
        env["list"] = {"title": str(env["list"].get("title", ""))[:60], "rows": [{"id": str(r["id"])[:64], "title": str(r["title"])[:24], **({"desc": str(r["desc"])[:72]} if r.get("desc") else {})} for r in rows[:10]]}
    if env.get("citations"):
        env["citations"] = [c for c in env["citations"] if c.get("type") in ("stock", "play", "forecast") and c.get("ref")]
    env["text"] = str(env.get("text", ""))[:4096]
    return env


async def run_chat_async(store: LocalStore, session_id: str, text: str, customer_id: str | None = None, backend: str | None = None, now_iso: str | None = None) -> list[dict[str, Any]]:
    customer_id = customer_id or session_id.split(":", 1)[0]
    channel = "web_chat" if session_id.endswith(":web") else "whatsapp"
    now = now_iso or _now()
    tenant = load_tenant()
    ctx = CustomerContext.build(store, customer_id, now, tenant, channel)
    token = set_context(ctx)
    t0 = time.perf_counter()
    try:
        runner = _runner(store, backend)
        async with _SESSION_LOCK:
            session = await runner.session_service.get_session(app_name=APP, user_id=customer_id, session_id=session_id)
            if session is None:
                session = await runner.session_service.create_session(app_name=APP, user_id=customer_id, session_id=session_id)
                store.append("conversations", [{"tenant_id": tenant.tenant_id, "session_id": session_id, "customer_id": customer_id, "channel": channel, "play_id": None, "started_at": now}])
        msg = types.Content(role="user", parts=[types.Part(text=f"customer_id={customer_id} {text}".strip())])
        tool_calls: list[dict[str, Any]] = []
        final_text = ""
        async for ev in runner.run_async(user_id=customer_id, session_id=session.id, new_message=msg):
            for part in (ev.content.parts if ev.content and ev.content.parts else []):
                if part.function_call:
                    tool_calls.append({"name": part.function_call.name, "args": dict(part.function_call.args or {})})
                if part.function_response:
                    tool_calls.append({"name": part.function_response.name, "result_ref": f"{session_id}#{len(tool_calls)}"})
                if part.text and ev.author == "customer":
                    final_text = part.text
        latency_ms = int((time.perf_counter() - t0) * 1000)
        env = _clamp(_parse_envelope(final_text))
        envelope = {"session_id": session_id, "message_id": f"{session_id}-{int(time.time() * 1000)}", "role": "agent", "language": ctx.products and (store.find("customers", customer_id=customer_id) or [{}])[-1].get("language", "en") or "en", **env, "tool_calls": [{"name": t["name"], **({"args": t["args"]} if "args" in t else {}), **({"result_ref": t["result_ref"]} if "result_ref" in t else {})} for t in tool_calls][:20], "latency_ms": latency_ms, "ts": now}
        _VALIDATOR.validate(envelope)
        store.append("messages", [
            {"tenant_id": tenant.tenant_id, "session_id": session_id, "message_id": envelope["message_id"] + "-u", "customer_id": customer_id, "channel": channel, "role": "user", "text": text, "tool_calls": None, "citations": None, "latency_ms": None, "ts": now},
            {"tenant_id": tenant.tenant_id, "session_id": session_id, "message_id": envelope["message_id"], "customer_id": customer_id, "channel": channel, "role": "agent", "text": envelope["text"], "tool_calls": json.dumps(envelope["tool_calls"]), "citations": json.dumps(envelope.get("citations") or []), "latency_ms": latency_ms, "ts": now},
        ])
        return [envelope]
    finally:
        reset_context(token)


def run_chat(data_dir: str | Path | LocalStore, session_id: str, text: str, customer_id: str | None = None, **kw: Any) -> list[dict[str, Any]]:
    store = data_dir if isinstance(data_dir, LocalStore) else LocalStore(data_dir)
    return asyncio.run(run_chat_async(store, session_id, text, customer_id, **kw))


def reset_sessions() -> None:
    _RUNNERS.clear()
