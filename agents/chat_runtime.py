"""Shared chat runtime for every chat specialist (customer, stylist).

One ADK `InMemoryRunner` per (store root, backend) and per specialist app; the session key is
`customer_id:web`. A turn runs the agent, collects its tool calls, parses the JSON envelope the
prompt asks the model for (docs/schemas/chat_envelope.schema.json), clamps the interactive limits,
validates the envelope and persists both sides of the turn to `conversations` / `messages`.
Context building (which tables the tools may see) stays with each specialist.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import time
from collections.abc import Callable
from datetime import UTC, date, datetime
from typing import Any

import jsonschema
from google.adk.agents import LlmAgent
from google.adk.runners import InMemoryRunner, Runner
from google.genai import types

from agents.gate.config import ROOT, TenantConfig
from agents.gate.store import LocalStore
from agents.vertex_sessions import build_session_service

ENVELOPE_SCHEMA = json.loads((ROOT / "docs" / "schemas" / "chat_envelope.schema.json").read_text(encoding="utf-8"))
_VALIDATOR = jsonschema.Draft202012Validator(ENVELOPE_SCHEMA, format_checker=jsonschema.FormatChecker())
KANNADA_RE = re.compile(r"[ಀ-೿]")


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def as_of_for(store: LocalStore) -> date:
    """The tenant's as-of date from manifest.json (falling back to the base store of an overlay)."""
    mp = store.root / "manifest.json"
    if not mp.exists() and hasattr(store, "base"):
        mp = store.base.root / "manifest.json"
    return date.fromisoformat(json.loads(mp.read_text(encoding="utf-8"))["as_of"]) if mp.exists() else date.today()


def detect_lang(text: str, fallback: str) -> str:
    """Reply in the script the customer just typed in; fall back to their stored preference only
    when the message carries no script of its own (STOP, a button id, empty)."""
    if KANNADA_RE.search(text):
        return "kn"
    if re.search(r"[A-Za-z]{2,}", text):
        return "en"
    return fallback


def vertex_env(models: dict[str, Any]) -> None:
    """Point google-genai at Vertex AI for the project/location in config/models.toml."""
    os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "TRUE")
    if models["vertex"].get("location") and not os.environ.get("GOOGLE_CLOUD_LOCATION"):
        os.environ["GOOGLE_CLOUD_LOCATION"] = models["vertex"]["location"]


def chat_generate_config(models: dict[str, Any], thinking_key: str, temperature: float) -> types.GenerateContentConfig:
    """A reply here is a conversational turn, not a plan: it does not need a thinking budget.
    `config/models.toml` defines `thinking.customer`/`thinking.stylist` (both "low") for exactly
    this; without wiring it, chat inherits the model's default dynamic thinking on every turn."""
    config = types.GenerateContentConfig(temperature=temperature)
    level = models.get("thinking", {}).get(thinking_key, "low")
    model_id = models["ids"]["flash"]
    try:
        if model_id.startswith("gemini-3"):
            config.thinking_config = types.ThinkingConfig(thinking_level=level)  # type: ignore[attr-defined]
        else:
            config.thinking_config = types.ThinkingConfig(thinking_budget={"low": 0, "medium": 1024, "high": 4096}.get(level, 0))
    except Exception:  # older google-genai without ThinkingConfig: keep default
        pass
    return config


def parse_envelope(text: str) -> dict[str, Any]:
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


# Defense in depth, not the primary fix: the primary fix is that agents/customer/chat.py and
# agents/stylist/chat.py no longer inject raw JSON + a "don't quote this" instruction into a
# turn's own text (a live reply once echoed exactly that block back to a customer -- see
# eval/evaluation.md). A model can still occasionally quote a parenthetical context note despite
# being told not to, so strip anything shaped like one before it ever reaches a customer, rather
# than trusting the prompt alone a second time.
_INTERNAL_LEAK_RE = re.compile(r"\(known:.*?\)|\[internal[^\]]*\]", re.I | re.S)


def _strip_internal_leak(text: str) -> str:
    return _INTERNAL_LEAK_RE.sub("", text).strip()


def clamp(env: dict[str, Any]) -> dict[str, Any]:
    # A model turn can emit these keys as an explicit JSON `null` rather than omitting them.
    # The schema declares buttons/list as optional but typed array/object with no null variant
    # (docs/schemas/chat_envelope.schema.json), so a literal null passes this function unchanged
    # and then fails _VALIDATOR.validate() uncaught -- the documented live-chat 500. Pop the key
    # outright for any falsy value (None, [], {}) instead of leaving it in the envelope.
    if env.get("buttons"):
        env["buttons"] = [{"id": str(b["id"])[:64], "label": str(b["label"])[:20]} for b in env["buttons"][:3]]
    else:
        env.pop("buttons", None)
    if env.get("list"):
        rows = env["list"].get("rows") or []
        env["list"] = {"title": str(env["list"].get("title", ""))[:60], "rows": [{"id": str(r["id"])[:64], "title": str(r["title"])[:24], **({"desc": str(r["desc"])[:72]} if r.get("desc") else {})} for r in rows[:10]]}
    else:
        env.pop("list", None)
    if env.get("citations"):
        env["citations"] = [c for c in env["citations"] if c.get("type") in ("stock", "play", "forecast") and c.get("ref")]
    else:
        env.pop("citations", None)
    env["text"] = _strip_internal_leak(str(env.get("text", "")))[:4096]
    return env


class ChatRuntime:
    """Runner cache, session bookkeeping and the turn loop for one specialist app."""

    def __init__(self, app_name: str, agent_name: str, build_agent: Callable[[LocalStore, str | None], LlmAgent]):
        self.app_name = app_name
        self.agent_name = agent_name
        self._build_agent = build_agent
        self._runners: dict[str, InMemoryRunner | Runner] = {}
        self._lock = asyncio.Lock()

    def runner(self, store: LocalStore, backend: str | None) -> InMemoryRunner | Runner:
        key = f"{store.root}|{backend or ''}"
        if key not in self._runners:
            agent = self._build_agent(store, backend)
            # build_session_service() returns None (TAAL_SESSION_BACKEND unset, the default for
            # every deployment today) unless a Vertex AI Sessions backend was explicitly opted
            # into -- see agents/vertex_sessions.py for why this is a separate flag from
            # TAAL_MODEL_BACKEND, not the same one.
            session_service = build_session_service()
            if session_service is None:
                self._runners[key] = InMemoryRunner(agent=agent, app_name=self.app_name)
            else:
                from google.adk.artifacts.in_memory_artifact_service import InMemoryArtifactService
                from google.adk.memory.in_memory_memory_service import InMemoryMemoryService

                self._runners[key] = Runner(app_name=self.app_name, agent=agent, artifact_service=InMemoryArtifactService(), session_service=session_service, memory_service=InMemoryMemoryService())
        return self._runners[key]

    def reset(self) -> None:
        self._runners.clear()

    async def run_turn(self, store: LocalStore, session_id: str, text: str, customer_id: str, backend: str | None, now: str, tenant: TenantConfig, channel: str, language: str, extra_tool_calls: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        t0 = time.perf_counter()
        runner = self.runner(store, backend)
        async with self._lock:
            session = await runner.session_service.get_session(app_name=self.app_name, user_id=customer_id, session_id=session_id)
            if session is None:
                session = await runner.session_service.create_session(app_name=self.app_name, user_id=customer_id, session_id=session_id)
                store.append("conversations", [{"tenant_id": tenant.tenant_id, "session_id": session_id, "customer_id": customer_id, "channel": channel, "play_id": None, "started_at": now}])
        msg = types.Content(role="user", parts=[types.Part(text=f"customer_id={customer_id} {text}".strip())])
        tool_calls: list[dict[str, Any]] = list(extra_tool_calls or [])
        final_text = ""
        async for ev in runner.run_async(user_id=customer_id, session_id=session.id, new_message=msg):
            for part in (ev.content.parts if ev.content and ev.content.parts else []):
                if part.function_call:
                    tool_calls.append({"name": part.function_call.name, "args": dict(part.function_call.args or {})})
                if part.function_response:
                    tool_calls.append({"name": part.function_response.name, "result_ref": f"{session_id}#{len(tool_calls)}"})
                if part.text and ev.author == self.agent_name:
                    final_text = part.text
        latency_ms = int((time.perf_counter() - t0) * 1000)
        env = clamp(parse_envelope(final_text))
        envelope = {"session_id": session_id, "message_id": f"{session_id}-{int(time.time() * 1000)}", "role": "agent", "language": language, **env, "tool_calls": [{"name": t["name"], **({"args": t["args"]} if "args" in t else {}), **({"result_ref": t["result_ref"]} if "result_ref" in t else {})} for t in tool_calls][:20], "latency_ms": latency_ms, "ts": now}
        _VALIDATOR.validate(envelope)
        store.append("messages", [
            {"tenant_id": tenant.tenant_id, "session_id": session_id, "message_id": envelope["message_id"] + "-u", "customer_id": customer_id, "channel": channel, "role": "user", "text": text, "tool_calls": None, "citations": None, "latency_ms": None, "ts": now},
            {"tenant_id": tenant.tenant_id, "session_id": session_id, "message_id": envelope["message_id"], "customer_id": customer_id, "channel": channel, "role": "agent", "text": envelope["text"], "tool_calls": json.dumps(envelope["tool_calls"]), "citations": json.dumps(envelope.get("citations") or []), "latency_ms": latency_ms, "ts": now},
        ])
        return envelope
