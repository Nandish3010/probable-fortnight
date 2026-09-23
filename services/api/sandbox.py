"""Per-visitor judge-mode sandboxes (DECISIONS §5.6): an OverlayStore per visitor id over the base
tenant, keyed by the `X-Taal-Visitor` header or the `taal_visitor` cookie. Reset deletes only the
visitor's overlay; the base tenant (and BigQuery in production) is never touched.

Mutating requests (POST/PUT/PATCH/DELETE) MUST land in a visitor overlay, never the base tenant:
this is an unauthenticated public service, and a headerless mutating request used to fall through
to `LocalStore(base_dir())` and write the shared base tenant permanently for every visitor after
it. `store_for` now mints a fresh visitor id for any headerless mutating request and sets it as a
cookie, so the base tenant is read-only from the API's point of view -- only `make generate` and
the deploy pipeline write it."""
from __future__ import annotations

import os
import re
import secrets
from pathlib import Path

from fastapi import Request, Response

from agents.gate.store import LocalStore, OverlayStore

VISITOR_RE = re.compile(r"^[A-Za-z0-9_-]{4,64}$")
MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
VISITOR_COOKIE_MAX_AGE = 60 * 60 * 24 * 30  # 30 days


def base_dir() -> Path:
    return Path(os.environ.get("TAAL_DATA_DIR", ".local/data"))


def sandbox_root() -> Path:
    return Path(os.environ.get("TAAL_SANDBOX_DIR", str(base_dir().parent / "sandbox")))


def visitor_id(request: Request) -> str | None:
    vid = request.headers.get("x-taal-visitor") or request.cookies.get("taal_visitor")
    return vid if vid and VISITOR_RE.match(vid) else None


def store_for(request: Request, response: Response) -> LocalStore:
    vid = visitor_id(request)
    if not vid and request.method in MUTATING_METHODS:
        vid = secrets.token_urlsafe(18)
        response.set_cookie("taal_visitor", vid, max_age=VISITOR_COOKIE_MAX_AGE, httponly=True, samesite="lax")
    if not vid:
        return LocalStore(base_dir())
    return OverlayStore(base_dir(), sandbox_root() / vid)
