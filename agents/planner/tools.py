"""The six Planner tools (DECISIONS §5.3). Deterministic; contracts in docs/schemas/tools/planner.*.

get_gap, get_candidate_audiences, get_past_plays read the store; estimate_outcome and
check_guardrails wrap agents/gate; propose_play validates against play.schema.json, writes the play,
sets `guardrails_all_passed` in session state and escalates to end the LoopAgent.
"""
from __future__ import annotations

import json
import os
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

import jsonschema
from google.adk.tools.tool_context import ToolContext

from agents.gate import guardrails as gr
from agents.gate.config import ROOT
from agents.gate.estimator import EstimatorContext, GapFacts, Product, estimate
from agents.gate.invariants import check_play_money
from agents.gate.models import Play

from . import governor
from .context import PlannerContext, current

PLAY_SCHEMA = json.loads((ROOT / "docs" / "schemas" / "play.schema.json").read_text(encoding="utf-8"))
_VALIDATOR = jsonschema.Draft202012Validator(PLAY_SCHEMA, format_checker=jsonschema.FormatChecker())
DISCOUNT_MECHANICS = {"coupon", "outlet_markdown", "bundle"}
ONLINE_ONLY_BLOCKED = {"bundle", "usual_order_addon", "substitution", "preorder", "subscription_nudge", "coupon"}


# ----------------------------------------------------------------------------- helpers

def _product(ctx: PlannerContext, sku: str) -> Product:
    p = ctx.products[sku]
    return Product(sku=sku, category=p["category"], unit_cost=float(p["unit_cost"]), list_price=float(p["list_price"]), margin_floor_pct=ctx.tenant.margin_floor(p["category"]))


def _consented(ctx: PlannerContext, channel: str = "web_chat") -> frozenset[str]:
    return frozenset(r["customer_id"] for r in ctx.store.read("consent") if r["purpose"] == "marketing" and r["channel"] == channel and not r.get("withdrawn_at"))


def _recent_play_counts(ctx: PlannerContext) -> dict[str, int]:
    cutoff = (ctx.as_of - timedelta(days=7)).isoformat()
    counts: dict[str, int] = defaultdict(int)
    for a in ctx.store.read("play_assignments"):
        if a["arm"] == "treated" and a["assigned_at"][:10] >= cutoff:
            counts[a["customer_id"]] += 1
    return counts


def audience_customer_ids(ctx: PlannerContext, sku: str, node_ids: list[str], segment_ids: list[str] | None = None, min_affinity: float | None = None) -> list[str]:
    """Customers whose home node is in the target nodes' clusters, with affinity to the sku (or
    strong affinity to its category), optionally restricted to segments. Order is stable."""
    min_aff = ctx.tenant.thresholds.get("min_affinity", 0.3) if min_affinity is None else min_affinity
    clusters = {ctx.nodes[n]["cluster_id"] for n in node_ids if n in ctx.nodes}
    category = ctx.products[sku]["category"]
    cat_skus = {s for s, p in ctx.products.items() if p["category"] == category}
    aff_sku: dict[str, float] = {}
    aff_cat: dict[str, float] = defaultdict(float)
    for a in ctx.store.read("affinity"):
        if a["sku"] == sku:
            aff_sku[a["customer_id"]] = float(a["score"])
        elif a["sku"] in cat_skus:
            aff_cat[a["customer_id"]] = max(aff_cat[a["customer_id"]], float(a["score"]))
    out = []
    for c in ctx.store.read("customers"):
        if ctx.nodes.get(c["home_node_id"], {}).get("cluster_id") not in clusters:
            continue
        if segment_ids and c.get("segment_id") not in segment_ids:
            continue
        if aff_sku.get(c["customer_id"], 0.0) >= min_aff or aff_cat.get(c["customer_id"], 0.0) >= 0.6:
            out.append(c["customer_id"])
    return out


def _gap(ctx: PlannerContext, gap_id: str) -> dict[str, Any]:
    rows = ctx.store.find("gaps", gap_id=gap_id)
    if not rows:
        raise KeyError(f"unknown gap {gap_id}")
    return rows[-1]


def _estimator_context(ctx: PlannerContext, draft: dict[str, Any]) -> EstimatorContext:
    sku = draft["target"]["sku"]
    gap = _gap(ctx, draft["gap_id"])
    product = _product(ctx, sku)
    params = draft.get("mechanic_params") or {}
    partner = ctx.products.get(params.get("bundle_sku") or "", {})
    qtys = [int(ln["qty"]) for ln in ctx.store.read("order_lines") if ln["sku"] == sku]
    avg_qty = sum(qtys) / len(qtys) if qtys else 1.0
    priors = {(r["mechanic"], r["category"], r["segment_id"]): (float(r["alpha"]), float(r["beta"]), int(r["n_measured"])) for r in ctx.store.read("estimator_priors")}

    def lookup(key: tuple[str, str, str]):
        return priors.get(key) or priors.get((key[0], key[1], "*"))

    return EstimatorContext(
        product=product,
        gap=GapFacts(units_at_risk=int(gap["units_at_risk"]), rupees_at_stake=float(gap["rupees_at_stake"]), evidence=gap["evidence"]),
        audience_size_after_consent=int(draft["audience"]["size_after_consent"]),
        avg_qty_per_responder=round(avg_qty, 3), priors=lookup,
        transfer_cost_per_unit=float(ctx.tenant.thresholds.get("transfer_cost_per_unit_inr", 2.0)),
        baseline_forecast_units=float(gap["evidence"].get("projected_sellthrough") or 0.0),
        markdown_elasticity=float(ctx.tenant.thresholds.get("markdown_elasticity", 1.0)),
        bundle_partner_unit_cost=float(partner.get("unit_cost") or 0.0), bundle_partner_list_price=float(partner.get("list_price") or 0.0),
    )


def _guardrail_context(ctx: PlannerContext, draft: dict[str, Any]) -> gr.GuardrailContext:
    sku = draft["target"]["sku"]
    node_ids = draft["target"]["node_ids"]
    product = _product(ctx, sku)
    params = draft.get("mechanic_params") or {}
    partner = ctx.products.get(params.get("bundle_sku") or "", {})
    ids = audience_customer_ids(ctx, sku, node_ids, draft["audience"].get("segment_ids"))
    consented = _consented(ctx, "web_chat" if draft.get("channel") != "outlet" else "outlet")
    recent = _recent_play_counts(ctx)
    cap = int(ctx.tenant.thresholds.get("frequency_cap_per_7d", 2))
    subscribers = frozenset(c["customer_id"] for c in ctx.store.read("customers") if sku in (c.get("subscription_skus") or []))
    # audience after the consent, frequency-cap and subscription filters is what the gate sees
    filtered = gr.filter_audience_by_consent(ids, consented)
    filtered = gr.filter_audience_by_frequency_cap(filtered, recent, cap)
    if draft.get("mechanic") in DISCOUNT_MECHANICS:
        filtered = gr.filter_audience_by_subscription(filtered, subscribers)
    stockout = frozenset(g["sku"] for g in ctx.store.read("gaps") if g["type"] == "stockout_risk" and g["node_id"] in node_ids)
    gap_ids = {g["gap_id"] for g in ctx.store.read("gaps")}
    forecast_runs = {r["run_id"] for r in ctx.store.read("sense_runs")}
    batch_ids = {b["batch_id"] for b in ctx.store.read("inventory_batches")}
    outcome_plays = {o["play_id"] for o in ctx.store.read("play_outcomes")}

    def resolve(ctype: str, ref: str) -> bool:
        if ctype == "gap":
            return ref in gap_ids
        if ctype == "estimator":
            return ref.startswith("est-")
        if ctype == "policy":
            return ref == ctx.policy_version
        if ctype == "forecast":
            return ref in forecast_runs or ref == draft.get("_forecast_run_id")
        if ctype == "stock":
            return ref in batch_ids
        if ctype == "outcome":
            return ref in outcome_plays
        return False

    return gr.GuardrailContext(
        product=product, tenant=ctx.tenant, audience_customer_ids=filtered, recent_plays_count=recent, consented_customer_ids=consented,
        subscribers_for_sku=subscribers, stockout_gap_skus_at_node=stockout, resolve_citation=resolve,
        bundle_partner_unit_cost=float(partner.get("unit_cost") or 0.0), bundle_partner_list_price=float(partner.get("list_price") or 0.0),
    )


# ----------------------------------------------------------------------------- tools

def get_gap(gap_id: str) -> dict:
    """Return the gap row (type, sku, node, units at risk, deadline, rupees at stake, evidence)."""
    ctx = current()
    g = dict(_gap(ctx, gap_id))
    p = ctx.products.get(g["sku"], {})
    g["product"] = {"name": p.get("name"), "category": p.get("category"), "unit_cost": p.get("unit_cost"), "list_price": p.get("list_price"), "margin_floor_pct": ctx.tenant.margin_floor(p.get("category", "default")), "shelf_life_days": p.get("shelf_life_days")}
    g["node"] = {k: ctx.nodes.get(g["node_id"], {}).get(k) for k in ("name", "type", "cluster_id", "lead_time_days")}
    g["policy_version"] = ctx.policy_version
    g["bundle_partner_candidates"] = _bundle_partners(ctx, g["sku"], g["node_id"])
    g["transfer_candidates"] = _transfer_candidates(ctx, g["node_id"])
    inbound = sorted((i for i in ctx.store.read("inbound") if i["sku"] == g["sku"] and i["node_id"] == g["node_id"]), key=lambda i: i["eta"])
    if inbound:
        g["evidence"] = {**g["evidence"], "inbound_eta": inbound[0]["eta"], "inbound_qty": int(inbound[0]["qty"])}
    return g


def _bundle_partners(ctx: PlannerContext, sku: str, node_id: str) -> list[dict]:
    """Up to three partner SKUs in stock at the node from a complementary category, highest stock first."""
    category = ctx.products[sku]["category"]
    partner_cats = {"snacks": ["beverages"], "beverages": ["snacks"], "sweets": ["premium_tea", "beverages"], "premium_tea": ["sweets", "bakery"], "staples": ["staples"], "dairy": ["bakery"], "bakery": ["dairy"]}.get(category, ["snacks"])
    stock: dict[str, int] = defaultdict(int)
    for b in ctx.store.read("inventory_batches"):
        if b["node_id"] == node_id and b["expiry_date"] and b["expiry_date"] >= ctx.as_of.isoformat():
            stock[b["sku"]] += int(b["qty_on_hand"])
    out = []
    for psku, p in ctx.products.items():
        if psku != sku and p["category"] in partner_cats and stock.get(psku, 0) >= 50:
            out.append({"sku": psku, "name": p["name"], "list_price": float(p["list_price"]), "unit_cost": float(p["unit_cost"]), "qty_on_hand": stock[psku]})
    base = float(ctx.products[sku]["list_price"])
    out.sort(key=lambda r: (abs(r["list_price"] - base), -r["qty_on_hand"], r["sku"]))
    return out[:3]


def _transfer_candidates(ctx: PlannerContext, node_id: str) -> list[dict]:
    """Outlets in the same cluster (physical sale is allowed until expiry)."""
    cluster = ctx.nodes.get(node_id, {}).get("cluster_id")
    return [{"node_id": n["node_id"], "name": n["name"]} for n in ctx.nodes.values() if n["type"] == "outlet" and n["cluster_id"] == cluster]


def get_candidate_audiences(sku: str, node_ids: list[str], objective: str) -> list[dict]:
    """Segments reachable for this sku at these nodes: size before and after the consent filter, mean affinity."""
    ctx = current()
    ids = audience_customer_ids(ctx, sku, node_ids)
    consented = _consented(ctx)
    seg_of = {c["customer_id"]: c.get("segment_id") for c in ctx.store.read("customers")}
    names = {s["segment_id"]: s["name"] for s in ctx.store.read("segments")}
    aff = {a["customer_id"]: float(a["score"]) for a in ctx.store.read("affinity") if a["sku"] == sku}
    by_seg: dict[str, dict[str, Any]] = defaultdict(lambda: {"before": 0, "after": 0, "aff": []})
    for cid in ids:
        seg = seg_of.get(cid) or "seg_1"
        by_seg[seg]["before"] += 1
        if cid in consented:
            by_seg[seg]["after"] += 1
        by_seg[seg]["aff"].append(aff.get(cid, 0.0))
    out = []
    for seg, v in by_seg.items():
        out.append({"segment_id": seg, "name": names.get(seg, seg), "size_before_consent": v["before"], "size_after_consent": v["after"], "mean_affinity": round(sum(v["aff"]) / len(v["aff"]), 3) if v["aff"] else 0.0})
    out.sort(key=lambda r: (-r["size_after_consent"], r["segment_id"]))
    return out


def get_past_plays(sku: str, category: str, mechanic: str) -> list[dict]:
    """Past plays for the same sku or category and mechanic, with expected and measured units."""
    ctx = current()
    outcomes = {o["play_id"]: o for o in ctx.store.read("play_outcomes") if o["arm"] == "treated"}
    out = []
    for r in ctx.store.read("plays"):
        pj = json.loads(r["play_json"]) if isinstance(r.get("play_json"), str) else r.get("play_json") or {}
        if not pj or pj.get("mechanic") != mechanic:
            continue
        psku = pj["target"]["sku"]
        if psku != sku and ctx.products.get(psku, {}).get("category") != category:
            continue
        o = outcomes.get(pj["play_id"])
        out.append({"play_id": pj["play_id"], "mechanic": pj["mechanic"], "mechanic_params": pj.get("mechanic_params", {}), "expected_units": pj["expected_outcome"]["units"], "measured_units": (o or {}).get("units_target_lot") if o and o["status"] == "measured" else None, "status": pj["status"]})
    return out[:10]


DRAFT_SHAPE = {
    "gap_id": "gap id from get_gap",
    "objective": "clear_online_sellby | clear_expiry | prevent_stockout | rebalance | revive_slow_mover",
    "target": {"sku": "SKU", "node_ids": ["DS-07"], "batch_ids": ["B-..."], "units": 0, "deadline_date": "YYYY-MM-DD", "deadline_type": "online_sellby | expiry | lead_time"},
    "mechanic": "bundle | usual_order_addon | substitution | preorder | subscription_nudge | coupon | outlet_markdown | transfer_plus_nudge",
    "mechanic_params": {"discount_pct?": 0, "bundle_sku?": "SKU", "bundle_price?": 0, "transfer_to_node?": "OUT-01", "markdown_pct?": 0},
    "audience": {"segment_ids": ["seg_1"], "purpose": "marketing", "size_before_consent": 0, "size_after_consent": 0},
    "holdout": {"fraction": 0.1, "seed": "string", "min_treated_n": 20},
}


def _draft_problems(draft: Any) -> list[str]:
    """What a live model most often leaves out of a play_draft. Returned to the model as a tool
    error it can act on; raising here would abort the whole ADK loop instead."""
    if not isinstance(draft, dict):
        return ["play_draft must be a JSON object"]
    problems = []
    for key in ("gap_id", "mechanic"):
        if not draft.get(key):
            problems.append(f"{key} is required")
    target = draft.get("target")
    if not isinstance(target, dict):
        problems.append("target is required (object with sku, node_ids, batch_ids, units, deadline_date, deadline_type)")
    else:
        for key in ("sku", "node_ids"):
            if not target.get(key):
                problems.append(f"target.{key} is required")
    audience = draft.get("audience")
    if not isinstance(audience, dict):
        problems.append("audience is required (object with segment_ids, size_before_consent, size_after_consent)")
    elif not audience.get("segment_ids"):
        problems.append("audience.segment_ids is required")
    return problems


def _draft_error(problems: list[str]) -> dict:
    return {"error": "play_draft is incomplete: " + "; ".join(problems), "required_shape": DRAFT_SHAPE}


def _estimate_one(ctx: PlannerContext, play_draft: dict) -> dict:
    problems = _draft_problems(play_draft)
    if problems:
        return _draft_error(problems)
    try:
        return estimate(play_draft, _estimator_context(ctx, play_draft))
    except KeyError as e:
        return {"error": f"estimate_outcome: unknown reference {e}", "required_shape": DRAFT_SHAPE}


def estimate_outcomes(play_drafts: list[dict]) -> list[dict]:
    """Deterministic estimator, batched: one call estimates every candidate draft at once (each
    draft the same shape `estimate_outcome` used to take) instead of one round trip per candidate.
    Returns one result per draft, same order; a draft with a problem gets {"error", "required_shape"}
    in its slot rather than failing the whole batch."""
    ctx = current()
    return [_estimate_one(ctx, d) for d in play_drafts]


def check_guardrails(play_draft: dict) -> dict:
    """Run the eight guardrails on a draft; returns every rule with pass/fail and detail, plus
    all_passed. Same draft shape as estimate_outcome; an incomplete draft returns {"error"}."""
    ctx = current()
    problems = _draft_problems(play_draft)
    if problems:
        return _draft_error(problems)
    try:
        return gr.check(play_draft, _guardrail_context(ctx, play_draft))
    except KeyError as e:
        return {"error": f"check_guardrails: unknown reference {e}", "required_shape": DRAFT_SHAPE}


def propose_play(play: dict, tool_context: ToolContext) -> dict:
    """Validate the play against the JSON Schema and the gate, write it, and end the planning loop."""
    ctx = current()
    if isinstance(play, dict):
        # Server-owned fields. A live model will otherwise invent them: the first Vertex run wrote
        # created_at "2023-10-27" and copied the Sense run id into trace_ref.
        pinned = os.environ.get("TAAL_NOW")
        now = datetime.fromisoformat(pinned.replace("Z", "+00:00")).astimezone(UTC) if pinned else datetime.now(UTC)
        play["created_at"] = now.isoformat(timespec="seconds").replace("+00:00", "Z")
        play["status"] = "proposed"
        play["policy_version"] = ctx.policy_version
        play["trace_ref"] = f"events/{ctx.run_id}"
        play.pop("approved_at", None)
        play.pop("approved_by", None)
    errors = [f"{'/'.join(str(p) for p in e.path) or '$'}: {e.message}" for e in sorted(_VALIDATOR.iter_errors(play), key=lambda e: list(e.path))]
    if not errors:
        try:
            Play.model_validate(play)
        except Exception as e:  # pydantic drift is a contract failure, surfaced as an error
            errors.append(f"model: {e}")
    if not errors:
        gap = _gap(ctx, play["gap_id"])
        sellby_passed = bool(gap["evidence"].get("sellby_passed")) or (gap["deadline_type"] == "online_sellby" and gap["deadline_date"] < ctx.as_of.isoformat())
        if sellby_passed and play["mechanic"] in ONLINE_ONLY_BLOCKED:
            errors.append("target lot is past its online sell-by: only outlet_markdown or transfer_plus_nudge are allowed")
        check = gr.check(play, _guardrail_context(ctx, play))
        if not check["all_passed"]:
            errors.extend(f"guardrail {r['rule']}: {r['detail']}" for r in check["results"] if not r["passed"])
        else:
            play["guardrails"] = check["results"]
            product = _product(ctx, play["target"]["sku"])
            partner = ctx.products.get((play.get("mechanic_params") or {}).get("bundle_sku") or "", {})
            mismatches = check_play_money(
                play, product.unit_cost, product.list_price, int(gap["units_at_risk"]),
                bundle_partner_unit_cost=float(partner.get("unit_cost") or 0.0), bundle_partner_list_price=float(partner.get("list_price") or 0.0),
                transfer_cost_per_unit=float(ctx.tenant.thresholds.get("transfer_cost_per_unit_inr", 2.0)),
            )
            if mismatches:
                errors.extend(f"runtime invariant: {m}" for m in mismatches)
    if errors:
        tool_context.state["guardrails_all_passed"] = False
        return {"play_id": None, "valid": False, "errors": errors}
    play["cost"] = governor.cost_for_play(play, _gap(ctx, play["gap_id"]), ctx.tenant)
    ctx.store.upsert("plays", "play_id", {
        "tenant_id": ctx.tenant.tenant_id, "play_id": play["play_id"], "gap_id": play["gap_id"], "status": play["status"], "objective": play["objective"],
        "mechanic": play["mechanic"], "channel": play["channel"], "sku": play["target"]["sku"], "target_node_ids": play["target"]["node_ids"],
        "target_batch_ids": play["target"]["batch_ids"], "window_start": play["window"]["start"], "window_end": play["window"]["end"],
        "policy_version": play["policy_version"], "created_at": play["created_at"], "approved_at": play.get("approved_at"), "play_json": json.dumps(play, ensure_ascii=False),
    })
    tool_context.state["guardrails_all_passed"] = True
    tool_context.state["proposed_play_id"] = play["play_id"]
    tool_context.actions.escalate = True
    return {"play_id": play["play_id"], "valid": True, "errors": []}


# get_gap, get_candidate_audiences and get_past_plays are registered so the model can still call
# them if it wants a second look, but run.py fetches all three up front (deterministic reads, not
# a decision) and hands the results to the model as context -- the round trip these calls used to
# cost is gone from the common path.
TOOLS = [get_gap, get_candidate_audiences, get_past_plays, estimate_outcomes, check_guardrails, propose_play]
REQUIRED_ORDER = ["estimate_outcomes", "propose_play"]
