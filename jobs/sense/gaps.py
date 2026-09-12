"""Gap detection (DECISIONS §2.3) over batches, inbound and the node-level forecast.

Rupees at stake: write-off gaps (online_sellby_breach, expiry_writeoff, slow_mover, rebalance)
use units_at_risk x unit_cost; stockout_risk uses the lost margin units_short x (list - cost).
An independent SQL recomputation lives in data/bigquery/assertions/gap_rupees_recompute.sql.

Forecast units are allocated to a node's batches of the same sku in deadline order (FIFO by
online sell-by, then expiry), so a lot's projected sell-through is what is left after earlier
lots are sold. A lot whose online sell-by has passed can only move through outlets or be
written off; it yields an expiry_writeoff gap with evidence.sellby_passed=true, never an
online_sellby_breach.
"""
from __future__ import annotations

import hashlib
from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from agents.gate.config import TenantConfig
from agents.gate.store import LocalStore

from .forecast import HORIZON

PLANTED_IDS = {
    ("online_sellby_breach", "SKU-MASALA-CHIPS-200G", "DS-07"): "gap_chips_ds07",
    ("stockout_risk", "SKU-COLA-ZERO-500ML", "DS-07"): "gap_cola_ds07",
    ("stockout_risk", "SKU-COLA-ZERO-500ML", "DS-02"): "gap_cola_ds02",
    ("stockout_risk", "SKU-KAJU-KATLI-250G", "DS-01"): "gap_kaju_ds01",
    ("stockout_risk", "SKU-KAJU-KATLI-250G", "DS-03"): "gap_kaju_ds03",
    ("slow_mover", "SKU-QUINOA-500G", "OUT-02"): "gap_quinoa_out02",
    ("online_sellby_breach", "SKU-DARJEELING-TEA-100G", "DS-04"): "gap_tea_ds04",
}


def gap_id_for(gap_type: str, sku: str, node_id: str, batch_id: str | None) -> str:
    planted = PLANTED_IDS.get((gap_type, sku, node_id))
    if planted:
        return planted
    h = hashlib.sha256(f"{gap_type}|{sku}|{node_id}|{batch_id or ''}".encode()).hexdigest()[:10]
    return f"gap_{h}"


def _sum_p50(series: dict[str, float], start: date, end: date) -> float:
    return sum(v for d, v in series.items() if start <= date.fromisoformat(d) <= end)


def detect(store: LocalStore, forecast_rows: list[dict[str, Any]], as_of: date, tenant: TenantConfig, run_id: str) -> list[dict[str, Any]]:
    products = {p["sku"]: p for p in store.read("products")}
    nodes = {n["node_id"]: n for n in store.read("nodes")}
    batches = store.read("inventory_batches")
    inbound = store.read("inbound")
    fc: dict[tuple[str, str], dict[str, float]] = defaultdict(dict)
    for r in forecast_rows:
        fc[(r["sku"], r["node_id"])][r["date"]] = r["p50"]
    horizon_end = as_of + timedelta(days=HORIZON - 1)
    slow_days = int(tenant.thresholds.get("slow_mover_days", 21))
    tid = tenant.tenant_id
    gaps: list[dict[str, Any]] = []

    # category median velocity per node type for slow movers (from the forecast level)
    cat_vel: dict[tuple[str, str], list[float]] = defaultdict(list)
    for (sku, node_id), series in fc.items():
        p = products.get(sku)
        if p:
            cat_vel[(p["category"], nodes[node_id]["type"])].append(sum(series.values()) / HORIZON)
    cat_median = {}
    for k, vals in cat_vel.items():
        s = sorted(vals)
        cat_median[k] = s[len(s) // 2] if s else 0.0

    by_node_sku: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for b in batches:
        by_node_sku[(b["sku"], b["node_id"])].append(b)
    inbound_by: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for i in inbound:
        inbound_by[(i["sku"], i["node_id"])].append(i)

    writeoff_nodes: dict[str, list[tuple[str, int, str]]] = defaultdict(list)  # sku -> [(node, units, gap_id)]
    stockout_nodes: dict[str, list[tuple[str, int, str]]] = defaultdict(list)

    for (sku, node_id), lots in sorted(by_node_sku.items()):
        p = products.get(sku)
        if not p:
            continue
        node = nodes[node_id]
        series = fc.get((sku, node_id), {})
        on_hand = sum(int(b["qty_on_hand"]) for b in lots)
        margin_per_unit = round(float(p["list_price"]) - float(p["unit_cost"]), 2)
        # --- write-off gaps, FIFO allocation of forecast to lots by deadline
        lots_sorted = sorted(lots, key=lambda b: (b["online_sellby_date"] or "9999", b["expiry_date"] or "9999", b["batch_id"]))
        consumed_until: dict[str, float] = {}
        allocated = 0.0
        for b in lots_sorted:
            qty = int(b["qty_on_hand"])
            if qty <= 0:
                continue
            expiry = date.fromisoformat(b["expiry_date"]) if b["expiry_date"] else None
            sellby = date.fromisoformat(b["online_sellby_date"]) if b["online_sellby_date"] else None
            if expiry is None or expiry < as_of:
                continue
            is_online_node = node["type"] == "dark_store"
            sellby_passed = bool(sellby and sellby < as_of and p["is_food"])
            deadline = sellby if (is_online_node and p["is_food"] and not sellby_passed) else expiry
            if deadline > horizon_end:
                continue
            available = _sum_p50(series, as_of, deadline) - allocated
            projected = max(0.0, min(float(qty), available))
            allocated += projected
            units_at_risk = int(round(qty - projected))
            if units_at_risk < 1:
                continue
            gap_type = "online_sellby_breach" if deadline is sellby and not sellby_passed and is_online_node else "expiry_writeoff"
            deadline_type = "online_sellby" if gap_type == "online_sellby_breach" else "expiry"
            gid = gap_id_for(gap_type, sku, node_id, b["batch_id"])
            evidence = {
                "on_hand": qty, "projected_sellthrough": round(projected, 2), "forecast_run_id": run_id,
                "sellby_rule": tenant.sellby_rule.version, "inbound": int(sum(i["qty"] for i in inbound_by.get((sku, node_id), []))),
                "unit_cost": float(p["unit_cost"]), "margin_per_unit": margin_per_unit,
                "expiry_date": b["expiry_date"], "online_sellby_date": b["online_sellby_date"], "sellby_passed": sellby_passed,
                "sku_name": p["name"], "category": p["category"], "node_type": node["type"],
            }
            gaps.append({
                "tenant_id": tid, "gap_id": gid, "run_id": run_id, "type": gap_type, "sku": sku, "node_id": node_id, "batch_id": b["batch_id"],
                "units_at_risk": units_at_risk, "deadline_date": deadline.isoformat(), "deadline_type": deadline_type,
                "rupees_at_stake": round(units_at_risk * float(p["unit_cost"]), 2), "evidence": evidence, "created_at": as_of.isoformat(),
            })
            writeoff_nodes[sku].append((node_id, units_at_risk, gid))
            consumed_until[b["batch_id"]] = projected
        # --- stockout risk over the lead time
        lead = int(node["lead_time_days"])
        lead_end = as_of + timedelta(days=lead)
        demand = _sum_p50(series, as_of, lead_end)
        arriving = sum(int(i["qty"]) for i in inbound_by.get((sku, node_id), []) if date.fromisoformat(i["eta"]) <= lead_end)
        short = demand - on_hand - arriving
        if short >= 1.0 and demand > 0:
            units_short = int(round(short))
            gid = gap_id_for("stockout_risk", sku, node_id, None)
            gaps.append({
                "tenant_id": tid, "gap_id": gid, "run_id": run_id, "type": "stockout_risk", "sku": sku, "node_id": node_id, "batch_id": None,
                "units_at_risk": units_short, "deadline_date": lead_end.isoformat(), "deadline_type": "lead_time",
                "rupees_at_stake": round(units_short * margin_per_unit, 2),
                "evidence": {"on_hand": on_hand, "projected_sellthrough": round(demand, 2), "forecast_run_id": run_id, "sellby_rule": tenant.sellby_rule.version,
                             "inbound": int(sum(i["qty"] for i in inbound_by.get((sku, node_id), []))), "unit_cost": float(p["unit_cost"]), "margin_per_unit": margin_per_unit,
                             "lead_time_days": lead, "sku_name": p["name"], "category": p["category"], "node_type": node["type"]},
                "created_at": as_of.isoformat(),
            })
            stockout_nodes[sku].append((node_id, units_short, gid))
        # --- slow mover
        vel = sum(series.values()) / HORIZON if series else 0.0
        median = cat_median.get((p["category"], node["type"]), 0.0)
        if on_hand > 0 and median > 0 and vel < 0.25 * median and on_hand > vel * slow_days:
            units = int(round(on_hand - vel * slow_days))
            lot = lots_sorted[0] if lots_sorted else None
            if units >= 1 and lot and lot["expiry_date"]:
                gid = gap_id_for("slow_mover", sku, node_id, lot["batch_id"])
                gaps.append({
                    "tenant_id": tid, "gap_id": gid, "run_id": run_id, "type": "slow_mover", "sku": sku, "node_id": node_id, "batch_id": lot["batch_id"],
                    "units_at_risk": units, "deadline_date": lot["expiry_date"], "deadline_type": "expiry",
                    "rupees_at_stake": round(units * float(p["unit_cost"]), 2),
                    "evidence": {"on_hand": on_hand, "projected_sellthrough": round(vel * slow_days, 2), "forecast_run_id": run_id, "sellby_rule": tenant.sellby_rule.version,
                                 "unit_cost": float(p["unit_cost"]), "margin_per_unit": margin_per_unit, "velocity_per_day": round(vel, 3), "category_median_velocity": round(median, 3),
                                 "slow_mover_days": slow_days, "sku_name": p["name"], "category": p["category"], "node_type": node["type"]},
                    "created_at": as_of.isoformat(),
                })

    # --- rebalance: surplus at A, short at B, same sku, same cluster
    for sku, surplus in writeoff_nodes.items():
        for node_a, units_a, gid_a in surplus:
            for node_b, units_b, gid_b in stockout_nodes.get(sku, []):
                if node_a == node_b or nodes[node_a]["cluster_id"] != nodes[node_b]["cluster_id"]:
                    continue
                units = min(units_a, units_b)
                if units < 1:
                    continue
                p = products[sku]
                src = next(g for g in gaps if g["gap_id"] == gid_a)
                gaps.append({
                    "tenant_id": tid, "gap_id": gap_id_for("rebalance", sku, node_a, node_b), "run_id": run_id, "type": "rebalance", "sku": sku, "node_id": node_a, "batch_id": src["batch_id"],
                    "units_at_risk": units, "deadline_date": src["deadline_date"], "deadline_type": src["deadline_type"],
                    "rupees_at_stake": round(units * float(p["unit_cost"]), 2),
                    "evidence": {**src["evidence"], "counterpart_node_id": node_b, "counterpart_units": units_b, "counterpart_gap_id": gid_b},
                    "created_at": as_of.isoformat(),
                })
    gaps.sort(key=lambda g: (-g["rupees_at_stake"], g["gap_id"]))
    return gaps
