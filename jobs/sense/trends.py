"""Style demand-signal aggregation (DECISIONS §5.9): style_requests -> style_trends. Mirrors
jobs/sense/gaps.py's demand-signal reasoning but produces its own table, not a gap -- this is a
merchandising/manufacturing signal, not a supply-side gap to plan a play against (see the "phase 2"
note in DECISIONS §5.9 for a possible assortment_gap type later).

Pure aggregation, deterministic: no LLM decides which trend to raise or how big it is.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from agents.gate.config import TenantConfig
from agents.gate.store import LocalStore


def build_style_trends(store: LocalStore, as_of: date, tenant: TenantConfig, run_id: str, computed_at: str | None = None) -> list[dict[str, Any]]:
    lookback = as_of - timedelta(days=int(tenant.thresholds.get("style_trends_lookback_days", 30)))
    min_asks = int(tenant.thresholds.get("style_trends_min_asks", 2))
    computed_at = computed_at or f"{as_of.isoformat()}T00:00:00Z"

    groups: dict[tuple[str, str | None, str | None, str | None], dict[str, Any]] = defaultdict(lambda: {"asks": 0, "customers": set(), "unfulfilled": 0})
    for r in store.read("style_requests"):
        ts_date = r["ts"][:10]
        if ts_date < lookback.isoformat():
            continue
        key = (r["node_id"], r.get("garment_type"), r.get("colour_family"), r.get("occasion"))
        g = groups[key]
        g["asks"] += 1
        g["customers"].add(r["customer_id"])
        if not r.get("fulfilled"):
            g["unfulfilled"] += 1

    tenant_id = tenant.tenant_id
    rows: list[dict[str, Any]] = []
    for (node_id, garment_type, colour_family, occasion), g in groups.items():
        if g["asks"] < min_asks:
            continue
        rows.append({
            "tenant_id": tenant_id, "run_id": run_id, "node_id": node_id,
            "window_days": int(tenant.thresholds.get("style_trends_lookback_days", 30)),
            "garment_type": garment_type, "colour_family": colour_family, "occasion": occasion,
            "asks": g["asks"], "distinct_customers": len(g["customers"]), "unfulfilled_asks": g["unfulfilled"],
            "computed_at": computed_at,
        })
    rows.sort(key=lambda r: (-r["asks"], r["node_id"] or "", r["garment_type"] or "", r["colour_family"] or "", r["occasion"] or ""))
    return rows
