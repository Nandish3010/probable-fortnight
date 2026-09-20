"""Per-conversation context for the Stylist tools (store, tenant, as-of, apparel catalogue, style
profile), via its own ContextVar so a stylist turn never shares state with a customer turn even
when both run against the same session id."""
from __future__ import annotations

import contextvars
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from agents.chat_runtime import as_of_for
from agents.gate.config import TenantConfig, load_tenant
from agents.gate.store import LocalStore


@dataclass
class StylistContext:
    store: LocalStore
    tenant: TenantConfig
    as_of: date
    customer_id: str
    channel: str = "web_chat"
    now_iso: str = ""
    apparel: dict[str, dict[str, Any]] = field(default_factory=dict)
    profile: dict[str, Any] | None = None

    @classmethod
    def build(cls, store: LocalStore, customer_id: str, now_iso: str, tenant: TenantConfig | None = None, channel: str = "web_chat") -> StylistContext:
        tenant = tenant or load_tenant()
        as_of = as_of_for(store)
        ctx = cls(store=store, tenant=tenant, as_of=as_of, customer_id=customer_id, channel=channel, now_iso=now_iso)
        ctx.apparel = {p["sku"]: p for p in store.read("apparel_products")}
        rows = [r for r in store.read("customer_style_profile") if r["customer_id"] == customer_id and not r.get("withdrawn_at")]
        ctx.profile = rows[-1] if rows else None
        return ctx


_current: contextvars.ContextVar[StylistContext] = contextvars.ContextVar("taal_stylist_context")


def set_context(ctx: StylistContext) -> contextvars.Token:
    return _current.set(ctx)


def reset_context(token: contextvars.Token) -> None:
    _current.reset(token)


def current() -> StylistContext:
    try:
        return _current.get()
    except LookupError as e:
        raise RuntimeError("stylist tools called outside run_stylist_chat") from e


__all__ = ["StylistContext", "current", "reset_context", "set_context"]
