"""Durable storage for practitioner feedback, behind its own switch:

    TAAL_FEEDBACK_STORE=firestore   production: two Firestore collections, `feedback_responses`
                                    (answers) and `feedback_contacts` (name / email or phone),
                                    keyed by the same server-assigned response_id.
    TAAL_FEEDBACK_STORE=local       development and tests: two JSONL files under
                                    TAAL_FEEDBACK_DIR (default .local/feedback).

Deliberately independent of TAAL_SERVING_CACHE and of the demo tenant's LocalStore/OverlayStore:
Cloud Run scales to zero, so container writes are lost, and a visitor's sandbox is deleted by
"Reset demo data". Neither may ever hold a real response. With the switch unset the default is
`firestore` on Cloud Run (K_SERVICE is set there) and `local` everywhere else, so a deploy that
forgets the flag still does not write real answers to a disk that is about to disappear.

Contacts live apart from answers so that nothing that reads answers (the summary command, the
results page) can include them by accident: those readers never call `contacts()`.
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any, Protocol

RESPONSES = "feedback_responses"
CONTACTS = "feedback_contacts"


class FeedbackStore(Protocol):
    def add(self, record: dict[str, Any], contact: dict[str, Any] | None) -> None: ...
    def responses(self) -> list[dict[str, Any]]: ...
    def contacts(self) -> list[dict[str, Any]]: ...
    def delete(self, response_id: str) -> bool: ...


def feedback_backend() -> str:
    explicit = os.environ.get("TAAL_FEEDBACK_STORE")
    if explicit:
        if explicit not in ("firestore", "local"):
            raise ValueError(f"TAAL_FEEDBACK_STORE must be 'firestore' or 'local', got {explicit!r}")
        return explicit
    return "firestore" if os.environ.get("K_SERVICE") else "local"


def feedback_dir() -> Path:
    return Path(os.environ.get("TAAL_FEEDBACK_DIR", ".local/feedback"))


class LocalFeedbackStore:
    """Append-only JSONL, rewritten only by delete(). One process-wide lock: the API is a single
    uvicorn process locally, and this backend is not used on Cloud Run."""

    _lock = threading.Lock()

    def __init__(self, root: Path):
        self.root = root

    def _path(self, name: str) -> Path:
        return self.root / f"{name}.jsonl"

    def _read(self, name: str) -> list[dict[str, Any]]:
        p = self._path(name)
        if not p.exists():
            return []
        return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]

    def _append(self, name: str, row: dict[str, Any]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        with self._path(name).open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    def add(self, record: dict[str, Any], contact: dict[str, Any] | None) -> None:
        with self._lock:
            self._append(RESPONSES, record)
            if contact:
                self._append(CONTACTS, contact)

    def responses(self) -> list[dict[str, Any]]:
        return self._read(RESPONSES)

    def contacts(self) -> list[dict[str, Any]]:
        return self._read(CONTACTS)

    def delete(self, response_id: str) -> bool:
        found = False
        with self._lock:
            for name in (RESPONSES, CONTACTS):
                rows = self._read(name)
                kept = [r for r in rows if r.get("response_id") != response_id]
                if len(kept) != len(rows):
                    found = True
                    self._path(name).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in kept), encoding="utf-8")
        return found


class FirestoreFeedbackStore:
    """Thin wrapper over a real (or fake, in tests) `google.cloud.firestore.Client`, the same
    pattern as agents/gate/firestore_cache.py. `create()` rather than `set()`, so a response_id
    collision fails loudly instead of overwriting someone else's answers."""

    def __init__(self, client: Any):
        self._client = client

    def add(self, record: dict[str, Any], contact: dict[str, Any] | None) -> None:
        rid = record["response_id"]
        self._client.collection(RESPONSES).document(rid).create(record)
        if contact:
            self._client.collection(CONTACTS).document(rid).create(contact)

    def responses(self) -> list[dict[str, Any]]:
        return [s.to_dict() for s in self._client.collection(RESPONSES).stream()]

    def contacts(self) -> list[dict[str, Any]]:
        return [s.to_dict() for s in self._client.collection(CONTACTS).stream()]

    def delete(self, response_id: str) -> bool:
        found = False
        for name in (RESPONSES, CONTACTS):
            ref = self._client.collection(name).document(response_id)
            if ref.get().exists:
                ref.delete()
                found = True
        return found


_CLIENTS: dict[str, Any] = {}


def build_store(project: str | None = None) -> FeedbackStore:
    """Resolved per call (tests flip the env), but one Firestore client per project per process."""
    if feedback_backend() == "local":
        return LocalFeedbackStore(feedback_dir())
    proj = project or os.environ.get("GOOGLE_CLOUD_PROJECT", "amru-509214")
    if proj not in _CLIENTS:
        from google.cloud import firestore

        _CLIENTS[proj] = firestore.Client(project=proj)
    return FirestoreFeedbackStore(_CLIENTS[proj])
