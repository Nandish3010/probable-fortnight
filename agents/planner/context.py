"""Per-run context for the Planner tools: which store, tenant, policy and as-of date they read.

Set by `run_planner` through a ContextVar so concurrent runs against different visitor sandboxes
(services/api) never share state.
"""
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
class PlannerContext:
    store: LocalStore
    tenant: TenantConfig
    as_of: date
    policy_text: str
    policy_version: str
    run_id: str
    products: dict[str, dict[str, Any]] = field(default_factory=dict)
    nodes: dict[str, dict[str, Any]] = field(default_factory=dict)

    @classmethod
    def build(cls, data_dir: str | Path, run_id: str, policy_text: str | None = None, policy_version: str | None = None, tenant: TenantConfig | None = None) -> PlannerContext:
        store = LocalStore(data_dir)
        tenant = tenant or load_tenant()
        manifest_path = store.root / "manifest.json"
        as_of = date.fromisoformat(json.loads(manifest_path.read_text(encoding="utf-8"))["as_of"]) if manifest_path.exists() else date.today()
        policy = store.read("policy")
        current = policy[-1] if policy else {"policy_version": tenant.policy_version, "text": tenant.policy_text}
        ctx = cls(
            store=store, tenant=tenant, as_of=as_of, run_id=run_id,
            policy_text=policy_text if policy_text is not None else current["text"],
            policy_version=policy_version or current["policy_version"],
        )
        ctx.products = {p["sku"]: p for p in store.read("products")}
        ctx.nodes = {n["node_id"]: n for n in store.read("nodes")}
        return ctx


_current: contextvars.ContextVar[PlannerContext] = contextvars.ContextVar("taal_planner_context")


def set_context(ctx: PlannerContext) -> contextvars.Token:
    return _current.set(ctx)


def reset_context(token: contextvars.Token) -> None:
    _current.reset(token)


def current() -> PlannerContext:
    try:
        return _current.get()
    except LookupError:
        # `adk eval` / `adk web` call the tools without run_planner: fall back to TAAL_DATA_DIR.
        import os

        ctx = PlannerContext.build(os.environ.get("TAAL_DATA_DIR", ".local/data"), run_id="adk-cli")
        _current.set(ctx)
        return ctx
