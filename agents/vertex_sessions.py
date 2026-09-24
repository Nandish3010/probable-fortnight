"""VertexAiSessionService wiring for Vertex AI Sessions (Agent Engine), item 4 of the "make the
architecture true" review: sessions currently die with the container because
`agents/customer/chat.py` and `agents/planner/run.py` construct `InMemoryRunner` unconditionally,
which hardcodes an in-process `InMemorySessionService`.

Deliberately behind a NEW, separate opt-in (`TAAL_SESSION_BACKEND=vertex`), never tied to
`TAAL_MODEL_BACKEND`: the deployed judged Cloud Run service already runs with
`TAAL_MODEL_BACKEND=vertex` (real Gemini), so if this were gated on that same flag, wiring it in
would silently change live production session behaviour the moment this merges. Decoupling the
two means the current deployment is completely unaffected until someone sets the new env var and
redeploys deliberately -- the live redeploy is not done in this change (see eval/evaluation.md).

Two real, load-bearing incompatibilities were found by actually calling the real service, not
guessed from docs, and are the reason this wrapper exists instead of passing `VertexAiSessionService`
straight to `Runner`:
1. Every session id in this codebase is `customer_id:web` / `customer_id:whatsapp`
   (services/api/main.py's own ChatRequest pattern: `^[A-Za-z0-9_-]+:(web|whatsapp)$`). Vertex's
   REAL server-side validation (found from the actual 400 response, stricter than the client
   library's own pre-check) is "session_id can only contain lowercase letters, digits and
   hyphens" -- a colon, an underscore, or any uppercase letter is rejected outright.
2. Every customer_id in this tenant is uppercase (`CUST-MEENA`, `CUST-00316`, ...), which fails
   that same real constraint when used as Vertex's `user_id`.

`_vertex_safe()` maps a real id to one that passes; `VertexSafeSessionService` wraps a real
`VertexAiSessionService` so every OTHER call site in this codebase (agents/chat_runtime.py,
agents/planner/run.py) keeps passing and receiving the original, unmodified ids -- the
translation is invisible outside this module. Verified for real against a real Agent Engine
instance (`eval/raw/vertex_sessions_2026-09-24/summary.json`): a session created through one
instance of this wrapper is correctly read back by a SECOND, independent instance (simulating a
container restart, which is the entire point of this item).
"""
from __future__ import annotations

import os
import re
from typing import Any

from google.adk.sessions import BaseSessionService


def vertex_safe_id(raw_id: str) -> str:
    """Lossy but collision-free for every id this tenant actually uses (hyphen-separated,
    already-distinct strings like `CUST-MEENA` or `CUST-00316:web`): lowercase, then any
    character outside [a-z0-9-] becomes a hyphen, collapsing repeats and trimming the ends
    (Vertex also requires the first/last character to be a letter or digit)."""
    s = re.sub(r"[^a-z0-9-]", "-", raw_id.lower())
    s = re.sub(r"-+", "-", s).strip("-")
    if not s:
        raise ValueError(f"id {raw_id!r} has no valid characters left for a Vertex session/user id")
    return s


def _retranslated(session: Any, user_id: str, session_id: str) -> Any:
    if session is not None:
        session.user_id, session.id = user_id, session_id
    return session


class VertexSafeSessionService(BaseSessionService):
    """Wraps a real `VertexAiSessionService`, translating ids on the way in and restoring the
    original ids on every `Session` object returned, so callers never see the translation.

    Must actually SUBCLASS `BaseSessionService`, not just duck-type its methods -- found by
    running this against a real `Runner` turn: ADK's `InvocationContext` is a pydantic model
    with `session_service: BaseSessionService`, and pydantic's `isinstance` field validation
    rejects a plain wrapper object outright ("Input should be an instance of
    BaseSessionService") even though it implements every method with the right signature.
    """

    def __init__(self, inner: Any):
        self._inner = inner

    async def create_session(self, *, app_name: str, user_id: str, state: dict | None = None, session_id: str | None = None) -> Any:
        session = await self._inner.create_session(app_name=app_name, user_id=vertex_safe_id(user_id), state=state, session_id=(vertex_safe_id(session_id) if session_id else None))
        return _retranslated(session, user_id, session_id or session.id)

    async def get_session(self, *, app_name: str, user_id: str, session_id: str, config: Any = None) -> Any:
        session = await self._inner.get_session(app_name=app_name, user_id=vertex_safe_id(user_id), session_id=vertex_safe_id(session_id), config=config)
        return _retranslated(session, user_id, session_id)

    async def delete_session(self, *, app_name: str, user_id: str, session_id: str) -> None:
        await self._inner.delete_session(app_name=app_name, user_id=vertex_safe_id(user_id), session_id=vertex_safe_id(session_id))

    async def list_sessions(self, *, app_name: str, user_id: str | None = None) -> Any:
        # Real ids in the response's sessions[] would come back translated (Vertex's own),
        # not this codebase's originals -- there is no way to reverse a lossy translation
        # (vertex_safe_id is not injective; two different real ids could collide on the safe
        # form). Not called by chat_runtime.py/planner/run.py today; raising loudly rather than
        # returning silently-wrong ids if something starts calling it.
        raise NotImplementedError("VertexSafeSessionService.list_sessions would return untranslated (lossy) ids -- not safe to use as-is; no caller needs this today")

    async def append_event(self, session: Any, event: Any) -> Any:
        # The Runner passes back the same Session object create_session/get_session returned
        # (original-format ids, per above); the inner service's append_event needs session.id/
        # session.user_id to match what IT issued, so translate on a copy, never the caller's
        # own object.
        import copy

        safe_session = copy.copy(session)
        safe_session.user_id, safe_session.id = vertex_safe_id(session.user_id), vertex_safe_id(session.id)
        return await self._inner.append_event(safe_session, event)


def build_session_service(agent_engine_id: str | None = None, project: str | None = None, location: str | None = None) -> Any:
    """The one entry point agents/chat_runtime.py and agents/planner/run.py call. Returns None
    (meaning: use the caller's existing InMemorySessionService-backed InMemoryRunner, unchanged)
    unless TAAL_SESSION_BACKEND=vertex is explicitly set -- so importing this module and calling
    this function has zero effect on any existing deployment until that new env var is set."""
    if os.environ.get("TAAL_SESSION_BACKEND") != "vertex":
        return None
    from google.adk.sessions import VertexAiSessionService

    engine_id = agent_engine_id or os.environ["TAAL_AGENT_ENGINE_ID"]
    proj = project or os.environ.get("GOOGLE_CLOUD_PROJECT", "amru-509214")
    loc = location or os.environ.get("TAAL_REGION", "asia-south1")
    return VertexSafeSessionService(VertexAiSessionService(project=proj, location=loc, agent_engine_id=engine_id))
