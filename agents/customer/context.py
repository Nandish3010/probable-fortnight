"""Per-conversation context for the Customer tools (store, tenant, as-of), via ContextVar."""
from __future__ import annotations

import contextvars
import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from agents.gate.config import TenantConfig, load_tenant
from agents.gate.store import LocalStore


@dataclass
class CustomerContext:
    store: LocalStore
    tenant: TenantConfig
    as_of: date
    customer_id: str
    channel: str = "web_chat"
    now_iso: str = ""
    products: dict[str, dict[str, Any]] = field(default_factory=dict)

    @classmethod
    def build(cls, store: LocalStore, customer_id: str, now_iso: str, tenant: TenantConfig | None = None, channel: str = "web_chat") -> CustomerContext:
        tenant = tenant or load_tenant()
        mp = store.root / "manifest.json"
        if not mp.exists() and hasattr(store, "base"):
            mp = store.base.root / "manifest.json"
        as_of = date.fromisoformat(json.loads(mp.read_text(encoding="utf-8"))["as_of"]) if mp.exists() else date.today()
        ctx = cls(store=store, tenant=tenant, as_of=as_of, customer_id=customer_id, channel=channel, now_iso=now_iso)
        ctx.products = {p["sku"]: p for p in store.read("products")}
        return ctx


_current: contextvars.ContextVar[CustomerContext] = contextvars.ContextVar("taal_customer_context")


def set_context(ctx: CustomerContext) -> contextvars.Token:
    return _current.set(ctx)


def reset_context(token: contextvars.Token) -> None:
    _current.reset(token)


def current() -> CustomerContext:
    try:
        return _current.get()
    except LookupError as e:
        raise RuntimeError("customer tools called outside run_chat") from e


__all__ = ["CustomerContext", "Path", "current", "reset_context", "set_context"]
