"""Per-visitor judge-mode sandboxes (DECISIONS §5.6): an OverlayStore per visitor id over the base
tenant, keyed by the `X-Taal-Visitor` header or the `taal_visitor` cookie. Reset deletes only the
visitor's overlay; the base tenant (and BigQuery in production) is never touched."""
from __future__ import annotations

import os
import re
from pathlib import Path

from fastapi import HTTPException, Request

from agents.gate.store import LocalStore, OverlayStore

VISITOR_RE = re.compile(r"^[A-Za-z0-9_-]{4,64}$")

# A headerless mutating request used to silently write into the shared base tenant -- a real,
# permanent, unauthenticated write to state every visitor's judge-mode session reads, on a
# public service with no auth. GET requests still fall back to the base tenant (read-only, and
# the whole point of judge mode is that a first-time visitor with no cookie yet can see the
# seeded demo state before ever writing to it). /reset is exempt: its own handler already
# guards this correctly (isinstance(store, OverlayStore)) and returns a safe no-op {"ok": False}
# for the base tenant rather than mutating anything, which is a real, already-tested contract
# (tests/api/test_api.py::test_two_visitors_are_isolated_and_reset_is_scoped) -- rejecting it
# here too would just turn that documented no-op into a 400.
_MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
_EXEMPT_PATHS = {"/reset"}


def base_dir() -> Path:
    return Path(os.environ.get("TAAL_DATA_DIR", ".local/data"))


def sandbox_root() -> Path:
    return Path(os.environ.get("TAAL_SANDBOX_DIR", str(base_dir().parent / "sandbox")))


def visitor_id(request: Request) -> str | None:
    vid = request.headers.get("x-taal-visitor") or request.cookies.get("taal_visitor")
    return vid if vid and VISITOR_RE.match(vid) else None


def store_for(request: Request) -> LocalStore:
    vid = visitor_id(request)
    if not vid:
        if request.method in _MUTATING_METHODS and request.url.path not in _EXEMPT_PATHS:
            raise HTTPException(status_code=400, detail="X-Taal-Visitor header or taal_visitor cookie is required for this request; it would otherwise write to the shared base tenant.")
        return LocalStore(base_dir())
    return OverlayStore(base_dir(), sandbox_root() / vid)
