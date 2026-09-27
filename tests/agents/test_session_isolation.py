"""Two visitors chatting as the same customer never see each other's turns.

With the in-memory backend each visitor's store root already gets its own runner (and so its own
InMemorySessionService). The shared case is what TAAL_SESSION_BACKEND=vertex turns on: ONE Agent
Engine behind every visitor's runner, where the session id is the only thing keeping two judges
who both chat as CUST-MEENA apart. That case is simulated here with one InMemorySessionService
shared by every runner; the live Agent Engine run is harness/live_sessions_cache.py.
"""
from __future__ import annotations

import asyncio

import pytest
from google.adk.sessions import InMemorySessionService

from agents import chat_runtime
from agents.chat_runtime import adk_ids, forget_persisted_sessions
from agents.customer.chat import APP, RUNTIME, reset_sessions, run_chat_async
from agents.gate.store import OverlayStore

NOW = "2026-09-12T09:05:00Z"
CUSTOMER = "CUST-MEENA"


def _texts(session) -> list[str]:
    return [p.text for ev in session.events if ev.content and ev.author == "user" for p in (ev.content.parts or []) if p.text]


def _history(store: OverlayStore, visitor: str) -> list[str]:
    user_id, session_id = adk_ids(visitor, CUSTOMER, f"{CUSTOMER}:web")
    session = asyncio.run(RUNTIME.runner(store, None).session_service.get_session(app_name=APP, user_id=user_id, session_id=session_id))
    assert session is not None, f"no session for visitor {visitor}"
    return _texts(session)


def _two_visitors(data_dir, tmp_path):
    a = OverlayStore(data_dir, tmp_path / "sandbox" / "visitor-aaaa")
    b = OverlayStore(data_dir, tmp_path / "sandbox" / "visitor-bbbb")
    return a, b


def _chat(store: OverlayStore, visitor: str, text: str) -> None:
    asyncio.run(run_chat_async(store, f"{CUSTOMER}:web", text, now_iso=NOW, visitor_id=visitor))


def test_adk_ids_are_visitor_scoped_and_keep_the_channel():
    assert adk_ids("v1", "CUST-MEENA", "CUST-MEENA:web") == ("v1:CUST-MEENA", "v1:CUST-MEENA:web")
    assert adk_ids("v1", "CUST-MEENA", "CUST-MEENA:whatsapp") == ("v1:CUST-MEENA", "v1:CUST-MEENA:whatsapp")
    assert adk_ids("v1", "CUST-MEENA", "CUST-MEENA:web") != adk_ids("v2", "CUST-MEENA", "CUST-MEENA:web")


def _assert_isolated(a, b):
    _chat(a, "visitor-aaaa", "Do you have Masala Chips?")
    _chat(b, "visitor-bbbb", "Do you have Cola Zero?")
    _chat(a, "visitor-aaaa", "Any offers?")
    hist_a, hist_b = _history(a, "visitor-aaaa"), _history(b, "visitor-bbbb")
    assert len(hist_a) == 2 and len(hist_b) == 1, (hist_a, hist_b)
    assert any("Masala Chips" in t for t in hist_a) and any("Any offers" in t for t in hist_a)
    assert not any("Cola Zero" in t for t in hist_a), "visitor A sees visitor B's turn"
    assert any("Cola Zero" in t for t in hist_b)
    assert not any("Masala Chips" in t or "Any offers" in t for t in hist_b), "visitor B sees visitor A's turns"


def test_two_visitors_same_customer_in_memory_backend(data_dir, tmp_path, monkeypatch):
    monkeypatch.delenv("TAAL_SESSION_BACKEND", raising=False)
    reset_sessions()
    a, b = _two_visitors(data_dir, tmp_path)
    _assert_isolated(a, b)


@pytest.fixture
def shared_session_service(monkeypatch):
    """Every runner gets the SAME session service, the way every visitor's runner reaches the
    same Agent Engine when TAAL_SESSION_BACKEND=vertex."""
    shared = InMemorySessionService()
    monkeypatch.setattr(chat_runtime, "build_session_service", lambda *a, **k: shared)
    reset_sessions()
    yield shared
    reset_sessions()


def test_two_visitors_same_customer_shared_session_service(data_dir, tmp_path, shared_session_service):
    a, b = _two_visitors(data_dir, tmp_path)
    _assert_isolated(a, b)
    sessions = asyncio.run(shared_session_service.list_sessions(app_name=APP))
    assert sorted(s.id for s in sessions.sessions) == ["visitor-aaaa:CUST-MEENA:web", "visitor-bbbb:CUST-MEENA:web"]


def test_session_survives_a_runner_rebuild_on_a_shared_service(data_dir, tmp_path, shared_session_service):
    """The in-process half of the restart test: dropping every runner (what a new process starts
    with) and chatting again resumes the same session from the shared service."""
    a, _ = _two_visitors(data_dir, tmp_path)
    _chat(a, "visitor-aaaa", "Do you have Masala Chips?")
    RUNTIME.reset()
    _chat(a, "visitor-aaaa", "Any offers?")
    hist = _history(a, "visitor-aaaa")
    assert len(hist) == 2 and "Masala Chips" in hist[0]
    assert len([r for r in a.read("conversations") if r["customer_id"] == CUSTOMER and r["started_at"] == NOW]) == 1, "a resumed session must not open a second conversation row"


def test_reset_forgets_only_the_resetting_visitors_persisted_session(data_dir, tmp_path, shared_session_service, monkeypatch):
    monkeypatch.setattr(chat_runtime, "build_session_service", lambda *a, **k: shared_session_service)
    a, b = _two_visitors(data_dir, tmp_path)
    _chat(a, "visitor-aaaa", "Do you have Masala Chips?")
    _chat(b, "visitor-bbbb", "Do you have Cola Zero?")
    deleted = asyncio.run(forget_persisted_sessions(a, "visitor-aaaa", [APP]))
    assert deleted == 1
    a.reset()
    reset_sessions(a)
    user_a, sid_a = adk_ids("visitor-aaaa", CUSTOMER, f"{CUSTOMER}:web")
    user_b, sid_b = adk_ids("visitor-bbbb", CUSTOMER, f"{CUSTOMER}:web")
    assert asyncio.run(shared_session_service.get_session(app_name=APP, user_id=user_a, session_id=sid_a)) is None
    assert asyncio.run(shared_session_service.get_session(app_name=APP, user_id=user_b, session_id=sid_b)) is not None
