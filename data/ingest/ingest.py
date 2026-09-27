"""Partner CSVs -> LocalStore tenant -> Sense -> "what Taal would have flagged".

Steps, each a function so tests and the round-trip harness can call them directly:
  load_and_validate()  every file against data/ingest/contract.py, plus cross-file checks
                       (unknown skus/nodes, duplicate keys); nothing is written if anything fails.
  build_tables()       the LocalStore rows the rest of the system reads, in the exact shapes
                       data/generator writes: online_sellby_date per batch under the tenant's
                       rule (agents/gate/sellby.py), future_regressors from the festival calendar.
  write_store()        TAAL_DATA_DIR-style JSONL + manifest.json.
  summarise()          the report: lots flagged under the sell-by rule, units and rupees at stake
                       by gap type, the ten largest gaps, and stock already past expiry.

Everything runs locally: the batch store and forecast backend are forced to `local` for this
process, so no row leaves the machine regardless of what the caller's environment sets.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from agents.gate.config import TenantConfig
from agents.gate.sellby import online_sellby_date
from agents.gate.store import LocalStore

from .contract import BATCHES, INBOUND, NODES, PRODUCTS, SALES, ContractError, read_csv

FESTIVALS = Path(__file__).resolve().parents[2] / "fixtures" / "festival_calendar.json"
REGRESSOR_DAYS = 28  # jobs/sense/forecast.py HORIZON; the generator writes the same window
DEFAULT_CLUSTER = "all"
SELLBY_TYPES = ("online_sellby_breach", "expiry_writeoff")
GROCERY_GAP_TYPES = ("online_sellby_breach", "expiry_writeoff", "stockout_risk", "rebalance", "slow_mover", "unmet_demand")


@dataclass
class Inputs:
    products: list[dict[str, Any]]
    batches: list[dict[str, Any]]
    sales: list[dict[str, Any]]
    nodes: list[dict[str, Any]] | None
    inbound: list[dict[str, Any]] | None
    warnings: list[str] = field(default_factory=list)
    sources: dict[str, str] = field(default_factory=dict)


def _sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_and_validate(products: str | Path, batches: str | Path, sales: str | Path,
                      nodes: str | Path | None = None, inbound: str | Path | None = None) -> Inputs:
    problems: list[str] = []
    p_rows, errs = read_csv(products, PRODUCTS)
    problems += errs
    b_rows, errs = read_csv(batches, BATCHES)
    problems += errs
    s_rows, errs = read_csv(sales, SALES)
    problems += errs
    n_rows = i_rows = None
    if nodes is not None:
        n_rows, errs = read_csv(nodes, NODES)
        problems += errs
    if inbound is not None:
        i_rows, errs = read_csv(inbound, INBOUND, allow_empty=True)
        problems += errs
    if problems:
        raise ContractError(problems)

    warnings: list[str] = []
    skus: set[str] = set()
    for i, p in enumerate(p_rows, start=2):
        if p["sku"] in skus:
            problems.append(f"{products}:{i}: duplicate sku {p['sku']!r}")
        skus.add(p["sku"])
    batch_ids: set[str] = set()
    for i, b in enumerate(b_rows, start=2):
        if b["batch_id"] in batch_ids:
            problems.append(f"{batches}:{i}: duplicate batch_id {b['batch_id']!r}")
        batch_ids.add(b["batch_id"])
    node_ids: set[str] | None = None
    if n_rows is not None:
        node_ids = set()
        for i, n in enumerate(n_rows, start=2):
            if n["node_id"] in node_ids:
                problems.append(f"{nodes}:{i}: duplicate node_id {n['node_id']!r}")
            node_ids.add(n["node_id"])
    for path, rows in ((batches, b_rows), (sales, s_rows), (inbound, i_rows or [])):
        unknown_sku = sorted({r["sku"] for r in rows} - skus)
        if unknown_sku:
            problems.append(f"{path}: {len(unknown_sku)} sku(s) not in products.csv, e.g. {', '.join(unknown_sku[:5])}")
        if node_ids is not None:
            unknown_node = sorted({r["node_id"] for r in rows} - node_ids)
            if unknown_node:
                problems.append(f"{path}: {len(unknown_node)} node_id(s) not in nodes.csv, e.g. {', '.join(unknown_node[:5])}")
    if problems:
        raise ContractError(problems)

    # Repeated (date, sku, node) sales rows are summed: an export at transaction grain still works.
    agg: dict[tuple[str, str, str], dict[str, Any]] = {}
    for r in s_rows:
        k = (r["date"], r["sku"], r["node_id"])
        if k in agg:
            a = agg[k]
            a["units"] += r["units"]
            a["revenue"] = None if a["revenue"] is None or r["revenue"] is None else round(a["revenue"] + r["revenue"], 2)
            a["on_promo"] = a["on_promo"] or r["on_promo"]
        else:
            agg[k] = dict(r)
    if len(agg) != len(s_rows):
        warnings.append(f"sales: {len(s_rows) - len(agg)} repeated (date, sku, node_id) row(s) summed into daily totals")
    if n_rows is None:
        warnings.append(f"no nodes.csv: every node_id is treated as an online dark store in one cluster ({DEFAULT_CLUSTER!r}); pass --nodes to set outlets, clusters and lead times")
    if i_rows is None:
        warnings.append("no inbound.csv: Sense sees no purchase orders in flight, so stockout_risk is an upper bound")
    sources = {"products": str(products), "inventory_batches": str(batches), "sales": str(sales)}
    if nodes is not None:
        sources["nodes"] = str(nodes)
    if inbound is not None:
        sources["inbound"] = str(inbound)
    return Inputs(p_rows, b_rows, list(agg.values()), n_rows, i_rows, warnings, sources)


def _future_regressors(tid: str, products: list[dict[str, Any]], clusters: list[str], as_of: date) -> list[dict[str, Any]]:
    """Festival flags per sku x cluster for the forecast window -- the same rule and calendar
    data/generator/generate.py::Generator.future_regressors uses, so a festival lift reaches a
    partner's categories only where their category names match the calendar's."""
    festivals = json.loads(FESTIVALS.read_text(encoding="utf-8"))["festivals"]
    rows = []
    for i in range(REGRESSOR_DAYS):
        d = as_of + timedelta(days=i)
        for p in products:
            fest = None
            for f in festivals:
                fd = date.fromisoformat(f["date"])
                if p["category"] in f["categories"] and fd - timedelta(days=f["window_days"]) <= d <= fd:
                    fest = f["name"]
            for cluster in clusters:
                rows.append({"tenant_id": tid, "date": d.isoformat(), "sku": p["sku"], "cluster_id": cluster, "on_promo": False, "is_festival": fest is not None, "festival_name": fest, "play_id": None})
    return rows


def default_as_of(inputs: Inputs) -> date:
    """The day after the last day of sales history: the first day Sense forecasts."""
    return date.fromisoformat(max(r["date"] for r in inputs.sales)) + timedelta(days=1)


def build_tables(inputs: Inputs, tenant: TenantConfig, as_of: date, default_lead_time_days: int = 3) -> dict[str, list[dict[str, Any]]]:
    tid = tenant.tenant_id
    rule = tenant.sellby_rule
    products = []
    for p in inputs.products:
        mf = p.get("margin_floor_pct")
        products.append({
            "tenant_id": tid, "sku": p["sku"], "name": p["name"], "category": p["category"], "pack_size": p.get("pack_size"),
            "pack_weight_g": p.get("pack_weight_g"), "unit_cost": p["unit_cost"], "list_price": p["list_price"],
            "margin_floor_pct": mf if mf is not None else tenant.margin_floor(p["category"]),
            "shelf_life_days": p["shelf_life_days"], "is_food": p["is_food"],
        })
    by_sku = {p["sku"]: p for p in products}
    if inputs.nodes is not None:
        nodes = [{"tenant_id": tid, "node_id": n["node_id"], "name": n["node_id"], "type": n["type"], "lat": n.get("lat"), "lng": n.get("lng"),
                  "lead_time_days": n["lead_time_days"], "cluster_id": n["cluster_id"]} for n in inputs.nodes]
    else:
        seen = sorted({r["node_id"] for r in inputs.batches} | {r["node_id"] for r in inputs.sales})
        nodes = [{"tenant_id": tid, "node_id": n, "name": n, "type": "dark_store", "lat": None, "lng": None,
                  "lead_time_days": default_lead_time_days, "cluster_id": DEFAULT_CLUSTER} for n in seen]
    batches = []
    for b in inputs.batches:
        p = by_sku[b["sku"]]
        expiry = date.fromisoformat(b["expiry_date"]) if b["expiry_date"] else None
        sellby = online_sellby_date(expiry, int(p["shelf_life_days"]), rule, bool(p["is_food"])) if expiry else None
        batches.append({
            "tenant_id": tid, "batch_id": b["batch_id"], "sku": b["sku"], "node_id": b["node_id"], "qty_on_hand": b["qty_on_hand"],
            "expiry_date": b["expiry_date"], "online_sellby_date": sellby.isoformat() if sellby else None,
            "received_at": b.get("received_at"), "source": b.get("source") or "system", "capture_ref": None, "sellby_rule_version": rule.version,
        })
    sales = [{"tenant_id": tid, "date": r["date"], "sku": r["sku"], "node_id": r["node_id"], "units": r["units"], "revenue": r.get("revenue"), "on_promo": r["on_promo"]}
             for r in inputs.sales]
    inbound = [{"tenant_id": tid, "po_id": r["po_id"], "sku": r["sku"], "node_id": r["node_id"], "qty": r["qty"], "eta": r["eta"]} for r in (inputs.inbound or [])]
    clusters = list(dict.fromkeys(n["cluster_id"] for n in nodes))
    return {
        "products": products, "nodes": nodes, "sales_daily": sales, "inventory_batches": batches, "inbound": inbound,
        "future_regressors": _future_regressors(tid, products, clusters, as_of),
    }


def write_store(out: str | Path, tables: dict[str, list[dict[str, Any]]], tenant: TenantConfig, as_of: date, inputs: Inputs, tenant_path: str | Path) -> LocalStore:
    out = Path(out)
    if out.exists() and any(out.glob("*.jsonl")):
        raise FileExistsError(f"{out} already holds a tenant store; pass an empty or new --out directory")
    store = LocalStore(out)
    for name, rows in tables.items():
        store.write(name, rows)
    manifest = {
        "tenant_id": tenant.tenant_id, "source": "data.ingest", "as_of": as_of.isoformat(), "sellby_rule": tenant.sellby_rule.version,
        "tenant_config": str(tenant_path), "counts": {k: len(v) for k, v in tables.items()},
        "inputs": {k: {"path": v, "sha256": _sha256(v)} for k, v in inputs.sources.items()}, "warnings": inputs.warnings,
    }
    (store.root / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return store


def summarise(store: LocalStore, as_of: date, sellby_rule: str, top_n: int = 10) -> dict[str, Any]:
    gaps = store.read("gaps")
    products = {p["sku"]: p for p in store.read("products")}
    by_type: dict[str, dict[str, float]] = {}
    for g in gaps:
        t = by_type.setdefault(g["type"], {"gaps": 0, "units_at_risk": 0, "rupees_at_stake": 0.0})
        t["gaps"] += 1
        t["units_at_risk"] += int(g["units_at_risk"])
        t["rupees_at_stake"] = round(t["rupees_at_stake"] + float(g["rupees_at_stake"]), 2)
    # "Flagged under the sell-by rule": a lot whose online sell-by date, not its printed expiry, is
    # the deadline it misses (online_sellby_breach), or whose sell-by has already passed so it can
    # only be written off or moved to a walk-in outlet (expiry_writeoff with sellby_passed).
    flagged = [g for g in gaps if g["type"] == "online_sellby_breach" or (g["type"] == "expiry_writeoff" and g["evidence"].get("sellby_passed"))]
    today = as_of.isoformat()
    # Stock at an online node whose online sell-by has passed but whose printed expiry has not: it
    # can no longer be sold online. Sense raises a gap for such a lot only when its expiry falls
    # inside the 28-day forecast horizon, so this is counted here straight from the batches.
    nodes = {n["node_id"]: n for n in store.read("nodes")}
    past_sellby = [b for b in store.read("inventory_batches")
                   if b["online_sellby_date"] and b["expiry_date"] and b["online_sellby_date"] < today <= b["expiry_date"]
                   and int(b["qty_on_hand"]) > 0 and nodes[b["node_id"]]["type"] == "dark_store" and products[b["sku"]]["is_food"]]
    expired = [b for b in store.read("inventory_batches") if b["expiry_date"] and b["expiry_date"] < today and int(b["qty_on_hand"]) > 0]
    expired_rupees = round(sum(int(b["qty_on_hand"]) * float(products[b["sku"]]["unit_cost"]) for b in expired), 2)
    top = sorted(gaps, key=lambda g: (-float(g["rupees_at_stake"]), g["gap_id"]))[:top_n]
    return {
        "as_of": as_of.isoformat(),
        "sellby_rule": sellby_rule,
        "gaps_total": len(gaps),
        "sellby_flagged": {
            "lots": len({g["batch_id"] for g in flagged}),
            "units_at_risk": sum(int(g["units_at_risk"]) for g in flagged),
            "rupees_at_stake": round(sum(float(g["rupees_at_stake"]) for g in flagged), 2),
            "sellby_already_passed_lots": sum(1 for g in flagged if g["type"] == "expiry_writeoff"),
        },
        "by_type": dict(sorted(by_type.items())),
        "top_gaps": [{"gap_id": g["gap_id"], "type": g["type"], "sku": g["sku"], "name": g["evidence"].get("sku_name"), "node_id": g["node_id"],
                      "batch_id": g["batch_id"], "units_at_risk": g["units_at_risk"], "rupees_at_stake": g["rupees_at_stake"],
                      "deadline_date": g["deadline_date"], "deadline_type": g["deadline_type"]} for g in top],
        "past_online_sellby_on_hand": {"lots": len(past_sellby), "units": sum(int(b["qty_on_hand"]) for b in past_sellby),
                                       "rupees_at_unit_cost": round(sum(int(b["qty_on_hand"]) * float(products[b["sku"]]["unit_cost"]) for b in past_sellby), 2),
                                       "in_a_gap": sum(1 for b in past_sellby if b["batch_id"] in {g["batch_id"] for g in flagged})},
        "already_expired_on_hand": {"lots": len(expired), "units": sum(int(b["qty_on_hand"]) for b in expired), "rupees_at_unit_cost": expired_rupees},
    }


def render(summary: dict[str, Any], currency: str = "INR") -> str:
    sym = "Rs " if currency == "INR" else f"{currency} "
    s = summary["sellby_flagged"]
    out = [
        f"As of {summary['as_of']} (sell-by rule {summary['sellby_rule']}): {summary['gaps_total']} gaps",
        "",
        f"Lots flagged under the online sell-by rule: {s['lots']} lots, {s['units_at_risk']:,} units, {sym}{s['rupees_at_stake']:,.2f} at stake"
        f" ({s['sellby_already_passed_lots']} of them with the online sell-by already passed)",
        "",
        "At stake by gap type (write-off types at unit cost; stockout/unmet demand at lost margin):",
    ]
    for t, v in summary["by_type"].items():
        out.append(f"  {t:<22} {v['gaps']:>5} gaps  {v['units_at_risk']:>9,} units  {sym}{v['rupees_at_stake']:>14,.2f}")
    out += ["", f"Ten largest gaps by {sym.strip()} at stake:"]
    for g in summary["top_gaps"]:
        out.append(f"  {sym}{g['rupees_at_stake']:>12,.2f}  {g['type']:<22} {g['sku']} @ {g['node_id']}  {g['units_at_risk']:,} units by {g['deadline_date']} ({g['deadline_type']})")
    p = summary["past_online_sellby_on_hand"]
    out += ["", f"Food at dark stores already past its online sell-by (outlet or write-off only): {p['lots']} lots, {p['units']:,} units, {sym}{p['rupees_at_unit_cost']:,.2f} at unit cost"
            f" ({p['in_a_gap']} of these lots are in a Sense gap; the rest expire after the 28-day horizon)"]
    e = summary["already_expired_on_hand"]
    out += ["", f"Already past printed expiry with stock on hand (a write-off already incurred): {e['lots']} lots, {e['units']:,} units, {sym}{e['rupees_at_unit_cost']:,.2f} at unit cost"]
    return "\n".join(out)


def force_local_backends() -> dict[str, str]:
    """Pin this process to the local store and forecaster and switch the serving cache off.
    Returns whatever the caller had set, so the CLI can say what it overrode."""
    overridden = {}
    for k, v in (("TAAL_BATCH_STORE", "local"), ("TAAL_FORECAST_BACKEND", "local")):
        if os.environ.get(k, v) != v:
            overridden[k] = os.environ[k]
        os.environ[k] = v
    if os.environ.get("TAAL_SERVING_CACHE"):
        overridden["TAAL_SERVING_CACHE"] = os.environ["TAAL_SERVING_CACHE"]
        del os.environ["TAAL_SERVING_CACHE"]
    return overridden

