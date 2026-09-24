"""agents.vertex_sessions: pure-logic tests -- this repo's unit tests never touch real GCP
credentials or network (see test_measure_cost.py's own header for the same convention). The real
create/get round trip across two independent VertexAiSessionService instances (simulating a
container restart) against a real Agent Engine was verified separately with a throwaway script;
raw evidence: eval/raw/vertex_sessions_2026-09-24/summary.json.
"""
from __future__ import annotations

import asyncio

import pytest

from agents.vertex_sessions import VertexSafeSessionService, build_session_service, vertex_safe_id


def test_vertex_safe_id_lowercases_and_replaces_disallowed_chars():
    assert vertex_safe_id("CUST-MEENA:web") == "cust-meena-web"
    assert vertex_safe_id("run_2e7621a152_v1_bcc00a4e") == "run-2e7621a152-v1-bcc00a4e"


def test_vertex_safe_id_collapses_and_trims():
    assert vertex_safe_id("CUST--00316::whatsapp") == "cust-00316-whatsapp"


def test_vertex_safe_id_rejects_empty_result():
    with pytest.raises(ValueError, match="no valid characters"):
        vertex_safe_id(":::")


def test_build_session_service_returns_none_by_default(monkeypatch):
    monkeypatch.delenv("TAAL_SESSION_BACKEND", raising=False)
    assert build_session_service() is None


def test_build_session_service_returns_none_when_backend_is_something_else(monkeypatch):
    monkeypatch.setenv("TAAL_SESSION_BACKEND", "local")
    assert build_session_service() is None


class _FakeSession:
    def __init__(self, id, app_name, user_id):
        self.id, self.app_name, self.user_id = id, app_name, user_id


class _FakeInnerService:
    def __init__(self):
        self.calls = []
        self._store = {}

    async def create_session(self, *, app_name, user_id, session_id=None, state=None):
        self.calls.append(("create_session", app_name, user_id, session_id))
        s = _FakeSession(session_id, app_name, user_id)
        self._store[(app_name, user_id, session_id)] = s
        return s

    async def get_session(self, *, app_name, user_id, session_id, config=None):
        self.calls.append(("get_session", app_name, user_id, session_id))
        return self._store.get((app_name, user_id, session_id))

    async def delete_session(self, *, app_name, user_id, session_id):
        self.calls.append(("delete_session", app_name, user_id, session_id))
        self._store.pop((app_name, user_id, session_id), None)

    async def append_event(self, session, event):
        self.calls.append(("append_event", session.app_name, session.user_id, session.id))
        return event


def test_wrapper_translates_ids_going_in_and_restores_them_coming_out():
    async def _run():
        inner = _FakeInnerService()
        wrapped = VertexSafeSessionService(inner)

        session = await wrapped.create_session(app_name="taal_customer", user_id="CUST-MEENA", session_id="CUST-MEENA:web")
        assert session.user_id == "CUST-MEENA" and session.id == "CUST-MEENA:web", "the caller must see the ORIGINAL ids back, not the translated ones"
        assert inner.calls[-1] == ("create_session", "taal_customer", "cust-meena", "cust-meena-web"), "the inner (real Vertex) call must use the TRANSLATED ids"

        fetched = await wrapped.get_session(app_name="taal_customer", user_id="CUST-MEENA", session_id="CUST-MEENA:web")
        assert fetched is not None and fetched.id == "CUST-MEENA:web"

    asyncio.run(_run())


def test_wrapper_get_session_returns_none_when_inner_has_nothing():
    async def _run():
        inner = _FakeInnerService()
        wrapped = VertexSafeSessionService(inner)
        result = await wrapped.get_session(app_name="taal_customer", user_id="CUST-X", session_id="CUST-X:web")
        assert result is None

    asyncio.run(_run())


def test_wrapper_append_event_translates_without_mutating_callers_session():
    async def _run():
        inner = _FakeInnerService()
        wrapped = VertexSafeSessionService(inner)
        session = await wrapped.create_session(app_name="taal_customer", user_id="CUST-MEENA", session_id="CUST-MEENA:web")
        await wrapped.append_event(session, {"text": "hi"})
        assert inner.calls[-1] == ("append_event", "taal_customer", "cust-meena", "cust-meena-web")
        # the caller's own Session object must be untouched by append_event's internal translation
        assert session.user_id == "CUST-MEENA" and session.id == "CUST-MEENA:web"

    asyncio.run(_run())


def test_wrapper_is_a_real_basesessionservice_subclass():
    # Not a duck-typed wrapper: ADK's InvocationContext is a pydantic model that validates its
    # session_service field with isinstance(value, BaseSessionService), which rejects a plain
    # wrapper class outright even if every method signature matches -- found by running this
    # against a real ADK Runner turn (see this module's own docstring).
    from google.adk.sessions import BaseSessionService

    assert isinstance(VertexSafeSessionService(_FakeInnerService()), BaseSessionService)


def test_wrapper_list_sessions_refuses_rather_than_return_lossy_ids():
    async def _run():
        wrapped = VertexSafeSessionService(_FakeInnerService())
        with pytest.raises(NotImplementedError, match="lossy"):
            await wrapped.list_sessions(app_name="taal_customer")

    asyncio.run(_run())


def test_wrapper_delete_session_translates_ids():
    async def _run():
        inner = _FakeInnerService()
        wrapped = VertexSafeSessionService(inner)
        await wrapped.create_session(app_name="taal_customer", user_id="CUST-MEENA", session_id="CUST-MEENA:web")
        await wrapped.delete_session(app_name="taal_customer", user_id="CUST-MEENA", session_id="CUST-MEENA:web")
        fetched = await wrapped.get_session(app_name="taal_customer", user_id="CUST-MEENA", session_id="CUST-MEENA:web")
        assert fetched is None

    asyncio.run(_run())
