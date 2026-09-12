"""Per-visitor judge-mode sandboxes (DECISIONS §5.6): an OverlayStore per visitor id over the base
tenant, keyed by the `X-Taal-Visitor` header or the `taal_visitor` cookie. Reset deletes only the
visitor's overlay; the base tenant (and BigQuery in production) is never touched."""
from __future__ import annotations

import os
import re
from pathlib import Path

from fastapi import Request

from agents.gate.store import LocalStore, OverlayStore

VISITOR_RE = re.compile(r"^[A-Za-z0-9_-]{4,64}$")


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
        return LocalStore(base_dir())
    return OverlayStore(base_dir(), sandbox_root() / vid)
