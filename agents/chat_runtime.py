"""Shared chat runtime for every chat specialist (customer).

One ADK runner per (store root, backend) and per specialist app. The ADK session is scoped to the
visitor as well as the customer (`adk_ids`): session_id `<visitor>:<customer_id>:web`, user_id
`<visitor>:<customer_id>`. With the in-memory backend the per-store-root runner already isolated
visitors; with the shared Vertex AI Sessions backend (TAAL_SESSION_BACKEND=vertex) the id is the
only thing that does, so two judges chatting as the same customer never share a session.

A turn runs the agent, collects its tool calls, parses the JSON envelope the prompt asks the model
for (docs/schemas/chat_envelope.schema.json), clamps the interactive limits, validates the envelope
and persists both sides of the turn to `conversations` / `messages`. Context building (which tables
the tools may see) stays with each specialist.
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

from agents.gate.config import ROOT, TenantConfig, load_models
from agents.gate.store import LocalStore
from agents.vertex_models import ModelUnavailable, failover_error, thinking_config
from agents.vertex_sessions import SESSION_IO_MS, build_session_service

ENVELOPE_SCHEMA = json.loads((ROOT / "docs" / "schemas" / "chat_envelope.schema.json").read_text(encoding="utf-8"))
_VALIDATOR = jsonschema.Draft202012Validator(ENVELOPE_SCHEMA, format_checker=jsonschema.FormatChecker())
KANNADA_RE = re.compile(r"[ಀ-೿]")


GLOSS_PREFIX = "English: "
GLOSS_MAX = 280
_KN_DIGITS = str.maketrans("೦೧೨೩೪೫೬೭೮೯", "0123456789")
_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")


def is_non_english(text: str) -> bool:
    return bool(KANNADA_RE.search(text))


def _numbers(text: str) -> set[float]:
    return {float(n) for n in _NUMBER_RE.findall(text.translate(_KN_DIGITS))}


def gloss_ok(gloss: str, text: str) -> bool:
    """A gloss may only restate the reply: every number in it (a price, a date, a count) must also
    be in the reply. One that adds a figure the reply never stated is dropped, not shown."""
    return _numbers(gloss) <= _numbers(text)


def with_gloss_prefix(gloss: str) -> str:
    gloss = gloss.strip()
    return (gloss if gloss.startswith(GLOSS_PREFIX) else GLOSS_PREFIX + gloss)[:GLOSS_MAX]


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


def chat_generate_config(models: dict[str, Any], thinking_key: str, temperature: float) -> types.GenerateContentConfig:
    """A reply here is a conversational turn, not a plan: it does not need a thinking budget.
    `config/models.toml` defines `thinking.customer` ("low") for exactly
    this; without wiring it, chat inherits the model's default dynamic thinking on every turn."""
    config = types.GenerateContentConfig(temperature=temperature)
    level = models.get("thinking", {}).get(thinking_key, "low")
    thinking = thinking_config(models["ids"]["flash"], level, default_budget=0)
    if thinking is not None:
        config.thinking_config = thinking
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


# Defense in depth, not the primary fix: the primary fix is that agents/customer/chat.py no longer injects raw JSON + a "don't quote this" instruction into a
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
    gloss = env.get("english_gloss")
    gloss = _strip_internal_leak(gloss) if isinstance(gloss, str) else ""
    if gloss:
        env["english_gloss"] = with_gloss_prefix(gloss)
    else:
        env.pop("english_gloss", None)
    return env


def resolve_gloss(env: dict[str, Any], tool_gloss: str | None, fallback: Callable[[dict[str, Any]], str | None] | None) -> None:
    """Settle `env["english_gloss"]` for a finished, clamped envelope, in place. Only a reply in
    another language gets one. Order: the English twin a tool composed next to its own receipt or
    refusal, else the model's gloss -- either kept only if it adds no number the reply lacks -- else
    the code's template from the structured fields (`fallback`, e.g. the offer being delivered)."""
    model_gloss = env.pop("english_gloss", None)
    if not is_non_english(env["text"]):
        return
    for candidate in (tool_gloss, model_gloss):
        if candidate and gloss_ok(candidate, env["text"]):
            env["english_gloss"] = with_gloss_prefix(candidate)
            return
    templated = fallback(env) if fallback else None
    if templated:
        env["english_gloss"] = with_gloss_prefix(templated)


def _log_timing(session_id: str, latency_ms: int, session_io: list[float]) -> None:
    """Opt-in (TAAL_CHAT_TIMING_LOG=<path>): one JSON line per turn splitting latency into
    session-service I/O vs the rest (model round trips, tools). Off by default; the envelope
    schema is closed, so the split cannot ride on the response itself."""
    path = os.environ.get("TAAL_CHAT_TIMING_LOG")
    if not path:
        return
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps({"session_id": session_id, "latency_ms": latency_ms, "session_io_ms": round(sum(session_io), 1), "session_calls": len(session_io)}) + "\n")


def visitor_for(store: LocalStore) -> str:
    """The visitor a store belongs to: an OverlayStore lives at `<sandbox root>/<visitor id>`
    (services/api/sandbox.py::store_for), the base tenant has no visitor."""
    return store.root.name if hasattr(store, "base") else "base"


def adk_ids(visitor_id: str, customer_id: str, session_id: str) -> tuple[str, str]:
    """(user_id, session_id) for the ADK session service. `session_id` is the API's own
    `customer_id:web|whatsapp`; only its channel suffix is kept. The API-facing session_id (the
    envelope, conversations, messages) is unchanged -- this is the session-service key only."""
    channel = session_id.rsplit(":", 1)[1] if ":" in session_id else "web"
    return f"{visitor_id}:{customer_id}", f"{visitor_id}:{customer_id}:{channel}"


async def forget_persisted_sessions(store: LocalStore, visitor_id: str, app_names: list[str]) -> int:
    """Delete this visitor's sessions from a persistent session service before their sandbox is
    reset; otherwise, with TAAL_SESSION_BACKEND=vertex, a reset sandbox would resume a conversation
    about orders and offers that no longer exist in it. A no-op (0) on the in-memory backend,
    where dropping the visitor's runners (ChatRuntime.reset) already forgets them. The customers
    are the ones this visitor opened a conversation as: rows in the overlay's `conversations`
    that the base tenant does not have. Must run before OverlayStore.reset() deletes them."""
    service = build_session_service()
    if service is None or not hasattr(store, "base"):
        return 0
    base_rows = {(r["session_id"], r["started_at"]) for r in store.base.read("conversations")}
    mine = {(r["customer_id"], r["session_id"]) for r in store.read("conversations") if (r["session_id"], r["started_at"]) not in base_rows}
    deleted = 0
    for customer_id, session_id in sorted(mine):
        user_id, adk_session_id = adk_ids(visitor_id, customer_id, session_id)
        for app_name in app_names:
            try:
                await service.delete_session(app_name=app_name, user_id=user_id, session_id=adk_session_id)
                deleted += 1
            except Exception:  # absent under this app (session absent under this app)
                pass
    return deleted


class ChatRuntime:
    """Runner cache, session bookkeeping and the turn loop for one specialist app."""

    def __init__(self, app_name: str, agent_name: str, build_agent: Callable[[LocalStore, str | None], LlmAgent], gloss_fallback: Callable[[LocalStore, str, dict[str, Any]], str | None] | None = None):
        self.app_name = app_name
        self._gloss_fallback = gloss_fallback
        self.agent_name = agent_name
        self._build_agent = build_agent
        self._runners: dict[str, InMemoryRunner | Runner] = {}
        # One lock per ADK session, guarding get-or-create against a double create. Not one lock
        # for the whole runtime: with Vertex sessions the get/create are network round trips, and
        # a runtime-wide lock would queue every concurrent visitor behind them.
        self._locks: dict[str, asyncio.Lock] = {}

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

    def reset(self, store: LocalStore | None = None) -> None:
        """Forget every runner, or only `store`'s (one visitor's) -- so one visitor's reset no
        longer drops every other visitor's in-memory conversation along with it."""
        if store is None:
            self._runners.clear()
            return
        prefix = f"{store.root}|"
        for key in [k for k in self._runners if k.startswith(prefix)]:
            del self._runners[key]

    async def run_turn(self, store: LocalStore, session_id: str, text: str, customer_id: str, backend: str | None, now: str, tenant: TenantConfig, channel: str, language: str, extra_tool_calls: list[dict[str, Any]] | None = None, visitor_id: str | None = None) -> dict[str, Any]:
        t0 = time.perf_counter()
        session_io: list[float] = []
        io_token = SESSION_IO_MS.set(session_io)
        try:
            return await self._run_turn(store, session_id, text, customer_id, backend, now, tenant, channel, language, extra_tool_calls, visitor_id, t0, session_io)
        finally:
            SESSION_IO_MS.reset(io_token)

    async def _run_turn(self, store: LocalStore, session_id: str, text: str, customer_id: str, backend: str | None, now: str, tenant: TenantConfig, channel: str, language: str, extra_tool_calls: list[dict[str, Any]] | None, visitor_id: str | None, t0: float, session_io: list[float]) -> dict[str, Any]:
        runner = self.runner(store, backend)
        adk_user_id, adk_session_id = adk_ids(visitor_id or visitor_for(store), customer_id, session_id)
        async with self._locks.setdefault(f"{store.root}|{adk_session_id}", asyncio.Lock()):
            session = await runner.session_service.get_session(app_name=self.app_name, user_id=adk_user_id, session_id=adk_session_id)
            if session is None:
                session = await runner.session_service.create_session(app_name=self.app_name, user_id=adk_user_id, session_id=adk_session_id)
                store.append("conversations", [{"tenant_id": tenant.tenant_id, "session_id": session_id, "customer_id": customer_id, "channel": channel, "play_id": None, "started_at": now}])
        msg = types.Content(role="user", parts=[types.Part(text=f"customer_id={customer_id} {text}".strip())])
        tool_calls: list[dict[str, Any]] = list(extra_tool_calls or [])
        final_text, reply, reply_en = "", "", ""
        try:
            async for ev in runner.run_async(user_id=adk_user_id, session_id=session.id, new_message=msg):
                for part in (ev.content.parts if ev.content and ev.content.parts else []):
                    if part.function_call:
                        tool_calls.append({"name": part.function_call.name, "args": dict(part.function_call.args or {})})
                    if part.function_response:
                        tool_calls.append({"name": part.function_response.name, "result_ref": f"{session_id}#{len(tool_calls)}"})
                        reply = (part.function_response.response or {}).get("reply") or reply
                        reply_en = (part.function_response.response or {}).get("reply_en") or reply_en
                    if part.text and ev.author == self.agent_name:
                        final_text = part.text
        except Exception as e:
            # With a distinct ids.fallback the agent's model is a FallbackModel (agents/vertex_models.py),
            # so an availability error that reaches here means the fallback failed too (or none is
            # configured): the API answers 503 model_unavailable, not an unhandled 500.
            if failover_error(e):
                raise ModelUnavailable(load_models()["ids"]["flash"], detail=str(e)[:200]) from e
            raise
        latency_ms = int((time.perf_counter() - t0) * 1000)
        _log_timing(session_id, latency_ms, session_io)
        env = clamp(parse_envelope(final_text))
        if reply:
            # A tool-composed receipt or refusal (place_order, apply_offer) replaces whatever the model wrote: amounts and refusals come from code.
            env["text"] = reply
        fallback = (lambda e: self._gloss_fallback(store, customer_id, e)) if self._gloss_fallback else None
        resolve_gloss(env, reply_en, fallback)
        envelope = {"session_id": session_id, "message_id": f"{session_id}-{int(time.time() * 1000)}", "role": "agent", "language": language, **env, "tool_calls": [{"name": t["name"], **({"args": t["args"]} if "args" in t else {}), **({"result_ref": t["result_ref"]} if "result_ref" in t else {})} for t in tool_calls][:20], "latency_ms": latency_ms, "ts": now}
        _VALIDATOR.validate(envelope)
        store.append("messages", [
            {"tenant_id": tenant.tenant_id, "session_id": session_id, "message_id": envelope["message_id"] + "-u", "customer_id": customer_id, "channel": channel, "role": "user", "text": text, "tool_calls": None, "citations": None, "latency_ms": None, "ts": now},
            {"tenant_id": tenant.tenant_id, "session_id": session_id, "message_id": envelope["message_id"], "customer_id": customer_id, "channel": channel, "role": "agent", "text": envelope["text"], "tool_calls": json.dumps(envelope["tool_calls"]), "citations": json.dumps(envelope.get("citations") or []), "latency_ms": latency_ms, "ts": now},
        ])
        return envelope
