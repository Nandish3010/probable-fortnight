"""services.feedback.store against a fake Firestore client (no credentials, no network -- the same
convention as test_firestore_cache.py) and the local JSONL backend. The Firestore path has NOT been
verified against a real database from this suite."""
from __future__ import annotations

import pytest

from services.feedback.store import (
    CONTACTS,
    RESPONSES,
    FirestoreFeedbackStore,
    LocalFeedbackStore,
    feedback_backend,
)


class _Snap:
    def __init__(self, data):
        self._data = data

    @property
    def exists(self):
        return self._data is not None

    def to_dict(self):
        return dict(self._data)


class _Doc:
    def __init__(self, docs, path):
        self._docs, self._path = docs, path

    def create(self, data):
        if self._path in self._docs:
            raise RuntimeError("409 already exists")
        self._docs[self._path] = dict(data)

    def get(self):
        return _Snap(self._docs.get(self._path))

    def delete(self):
        self._docs.pop(self._path, None)


class _Coll:
    def __init__(self, docs, name):
        self._docs, self._name = docs, name

    def document(self, doc_id):
        return _Doc(self._docs, (self._name, doc_id))

    def stream(self):
        return [_Snap(v) for (c, _), v in sorted(self._docs.items()) if c == self._name]


class _Client:
    def __init__(self):
        self.docs = {}

    def collection(self, name):
        return _Coll(self.docs, name)


def _rec(rid, source="test"):
    return {"response_id": rid, "submitted_at": "2026-09-26T10:00:00Z", "form_version": "2026-09-26.1", "mode": "self", "source": source, "answers": {"a1_role": "owner"}, "has_contact": False}


def test_backend_switch(monkeypatch):
    monkeypatch.delenv("TAAL_FEEDBACK_STORE", raising=False)
    monkeypatch.delenv("K_SERVICE", raising=False)
    assert feedback_backend() == "local"
    monkeypatch.setenv("K_SERVICE", "taal-agents")
    assert feedback_backend() == "firestore", "on Cloud Run an unset switch must not mean an ephemeral disk"
    monkeypatch.setenv("TAAL_FEEDBACK_STORE", "local")
    assert feedback_backend() == "local"
    monkeypatch.setenv("TAAL_SERVING_CACHE", "firestore")
    monkeypatch.setenv("TAAL_FEEDBACK_STORE", "local")
    assert feedback_backend() == "local", "not tied to the serving-cache switch"
    monkeypatch.setenv("TAAL_FEEDBACK_STORE", "bigquery")
    with pytest.raises(ValueError):
        feedback_backend()


def test_firestore_store_keeps_contacts_in_their_own_collection():
    c = _Client()
    s = FirestoreFeedbackStore(c)
    s.add(_rec("a" * 32), {"response_id": "a" * 32, "reach": "x@example.invalid"})
    s.add(_rec("b" * 32), None)
    assert {k for k in c.docs} == {(RESPONSES, "a" * 32), (RESPONSES, "b" * 32), (CONTACTS, "a" * 32)}
    assert "x@example.invalid" not in repr(s.responses())
    assert [r["response_id"] for r in s.contacts()] == ["a" * 32]


def test_firestore_create_never_overwrites():
    s = FirestoreFeedbackStore(_Client())
    s.add(_rec("a" * 32), None)
    with pytest.raises(RuntimeError):
        s.add(_rec("a" * 32), None)


@pytest.mark.parametrize("make", [lambda tmp: FirestoreFeedbackStore(_Client()), lambda tmp: LocalFeedbackStore(tmp / "fb")])
def test_delete_removes_answers_and_contact(make, tmp_path):
    s = make(tmp_path)
    s.add(_rec("a" * 32), {"response_id": "a" * 32, "name": "n"})
    s.add(_rec("b" * 32), None)
    assert s.delete("a" * 32) is True
    assert [r["response_id"] for r in s.responses()] == ["b" * 32] and s.contacts() == []
    assert s.delete("a" * 32) is False


def test_local_store_lives_outside_the_demo_tenant_and_sandboxes(monkeypatch):
    from services.api.sandbox import base_dir, sandbox_root
    from services.feedback.store import feedback_dir

    for var in ("TAAL_FEEDBACK_DIR", "TAAL_DATA_DIR", "TAAL_SANDBOX_DIR"):
        monkeypatch.delenv(var, raising=False)
    fd = feedback_dir().resolve()
    for other in (base_dir().resolve(), sandbox_root().resolve()):
        assert other not in fd.parents and fd != other
