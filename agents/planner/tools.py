"""The six Planner tools (DECISIONS §5.3). Deterministic; contracts in docs/schemas/tools/planner.*.

get_gap, get_candidate_audiences, get_past_plays read the store; estimate_outcome and
check_guardrails wrap agents/gate; propose_play validates against play.schema.json, writes the play,
sets `guardrails_all_passed` in session state and escalates to end the LoopAgent.
"""
from __future__ import annotations

import copy
import json
import os
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from typing import Any

import jsonschema
from google.adk.tools.tool_context import ToolContext

from agents.gate import guardrails as gr
from agents.gate.assignment import bucket
from agents.gate.config import ROOT
from agents.gate.estimator import (
    MARKDOWN_MECHANIC,
    EstimatorContext,
    GapFacts,
    Product,
    baseline_units_of,
    best_markdown,
    estimate,
)
from agents.gate.invariants import check_play_money
from agents.gate.models import Play
from agents.gate.untrusted import clean_text, clean_tree, strings_in

from . import governor
from .context import PlannerContext, current

PLAY_SCHEMA = json.loads((ROOT / "docs" / "schemas" / "play.schema.json").read_text(encoding="utf-8"))
_VALIDATOR = jsonschema.Draft202012Validator(PLAY_SCHEMA, format_checker=jsonschema.FormatChecker())
DISCOUNT_MECHANICS = {"coupon", "outlet_markdown", "bundle"}
ONLINE_ONLY_BLOCKED = {"bundle", "usual_order_addon", "substitution", "preorder", "subscription_nudge", "coupon", "markdown"}
CLEARING_GAP_TYPES = ("online_sellby_breach", "expiry_writeoff")


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


def derive_channel(draft: dict[str, Any]) -> str:
    """Channel is server-owned: a shelf markdown at the outlet is the only non-personal play;
    every other mechanic is a personal offer and goes out on web_chat."""
    return "outlet" if draft.get("mechanic") == "outlet_markdown" else "web_chat"  # `markdown` is a shelf price: web_chat is only the schema's value, nobody is messaged


def eligible_audience(ctx: PlannerContext, draft: dict[str, Any]) -> tuple[list[str], list[str]]:
    """(candidates, eligible): the customers the segments reach, then those left after the
    web_chat marketing-consent, frequency-cap and subscription filters. The one definition of
    "audience after consent": the gate sizes the play from it and Approve assigns from it."""
    if draft.get("mechanic") == MARKDOWN_MECHANIC:
        return [], []  # a price cut contacts no customer: no audience, no consent filter
    gap = _gap(ctx, draft["gap_id"])
    sku, node_ids = draft["target"]["sku"], draft["target"]["node_ids"]
    requesting = (gap.get("evidence") or {}).get("requesting_customer_ids")
    ids = audience_customer_ids(ctx, sku, node_ids, draft["audience"].get("segment_ids"), requesting_customer_ids=requesting)
    cap = int(ctx.tenant.thresholds.get("frequency_cap_per_7d", 2))
    eligible = gr.filter_audience_by_consent(ids, _consented(ctx, "web_chat"))
    eligible = gr.filter_audience_by_frequency_cap(eligible, _recent_play_counts(ctx), cap)
    if draft.get("mechanic") in DISCOUNT_MECHANICS:
        subscribers = frozenset(c["customer_id"] for c in ctx.store.read("customers") if sku in (c.get("subscription_skus") or []))
        eligible = gr.filter_audience_by_subscription(eligible, subscribers)
    return ids, list(eligible)


def comparable_at_risk_nodes(ctx: PlannerContext, gap: dict[str, Any]) -> list[str]:
    """Nodes of the same type as the gap's node where the same sku has an open clearing gap now (the gap's own
    node excluded): the candidates for a node-level holdout of a `markdown`."""
    ntype = ctx.nodes.get(gap["node_id"], {}).get("type")
    out = {g["node_id"] for g in ctx.store.read("gaps") if g["sku"] == gap["sku"] and g["type"] in CLEARING_GAP_TYPES and g["node_id"] != gap["node_id"] and ctx.nodes.get(g["node_id"], {}).get("type") == ntype}
    return sorted(out)


def apply_derived_markdown(ctx: PlannerContext, draft: dict[str, Any]) -> None:
    """Server-owned parts of a `markdown`: the target node is the gap's node, the end date is the sell-by line,
    no audience, and the measurement. A price cut cannot hold out customers. When the sku is at risk at 2+
    comparable nodes, the other at-risk node(s) keep the list price as a node holdout, chosen by the same
    deterministic hash as customer assignment (assignment.bucket, lowest bucket first; at least one node, at most
    all but the treated one, about the play's holdout fraction); otherwise measurement is "none" with the reason."""
    gap = _gap(ctx, draft["gap_id"])
    target = draft.setdefault("target", {})
    target["node_ids"] = [gap["node_id"]]
    params = draft.setdefault("mechanic_params", {})
    params["end_date"] = target.get("deadline_date") or gap["deadline_date"]
    draft["audience"] = {"segment_ids": ["all"], "filters": {}, "purpose": "marketing", "size_before_consent": 0, "size_after_consent": 0}
    h = draft.setdefault("holdout", {"fraction": float(ctx.tenant.thresholds.get("default_holdout_fraction", 0.10)), "seed": "markdown-seed", "min_treated_n": int(ctx.tenant.thresholds.get("min_treated_n", 20))})
    controls = comparable_at_risk_nodes(ctx, gap)
    h.pop("node_ids", None)
    if controls:
        seed = str(h.get("seed") or "markdown-seed")
        order = sorted(controls, key=lambda n: (bucket(n, seed), n))
        k = max(1, min(len(order), round(float(h.get("fraction") or 0.1) * (len(order) + 1))))
        held = order[:k]
        h.update({"measurement": "holdout_nodes", "node_ids": held, "measurement_reason": f"{len(held)} comparable at-risk node(s) keep the list price: {', '.join(held)}"})
        h["fraction"] = min(0.9, max(0.05, round(len(held) / (len(held) + 1), 2)))
    else:
        h.update({"measurement": "none", "measurement_reason": f"{gap['sku']} is at risk at no other comparable node, so there is no node to hold out; a price cut cannot hold out individual customers. This play cannot be measured against a holdout."})


def apply_derived_audience(ctx: PlannerContext, draft: dict[str, Any]) -> None:
    """Overwrite channel and audience sizes with the tools' own values, whatever the model wrote."""
    if draft.get("mechanic") == MARKDOWN_MECHANIC:
        apply_derived_markdown(ctx, draft)
    ids, eligible = eligible_audience(ctx, draft)
    draft["channel"] = derive_channel(draft)
    draft["audience"]["size_before_consent"] = len(ids)
    draft["audience"]["size_after_consent"] = len(eligible)
    if draft.get("mechanic") != MARKDOWN_MECHANIC and isinstance(draft.get("holdout"), dict):
        for key in ("measurement", "measurement_reason", "node_ids"):  # only a markdown has a non-customer measurement
            draft["holdout"].pop(key, None)


def rederive_play(ctx: PlannerContext, play: dict[str, Any]) -> None:
    """Re-derive channel, audience size and the estimate figures with the deterministic tools,
    overwriting what the planner model stated. Guardrails run after this on the corrected play."""
    apply_derived_audience(ctx, play)
    est = estimate(play, _estimator_context(ctx, play))
    play["expected_outcome"] = est["expected_outcome"]
    play["counterfactuals"] = est["counterfactuals"]


def audience_customer_ids(ctx: PlannerContext, sku: str, node_ids: list[str], segment_ids: list[str] | None = None, min_affinity: float | None = None, requesting_customer_ids: list[str] | None = None) -> list[str]:
    """Customers whose home node is in the target nodes' clusters, with affinity to the sku (or
    strong affinity to its category), optionally restricted to segments. Order is stable.

    `requesting_customer_ids` (assortment_gap's real askers, from gap evidence) are always
    included regardless of affinity: the affinity table only ever covers grocery skus, so a
    sku with no affinity rows yields an empty lookup, and a customer who is actually the source of
    the demand signal is stronger evidence than a modelled score anyway."""
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
    if requesting_customer_ids:
        seen = set(out)
        for cid in requesting_customer_ids:
            if cid not in seen:
                out.append(cid)
                seen.add(cid)
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
        audience_size_after_consent=int((draft.get("audience") or {}).get("size_after_consent") or 0),
        avg_qty_per_responder=round(avg_qty, 3), priors=lookup,
        transfer_cost_per_unit=float(ctx.tenant.thresholds.get("transfer_cost_per_unit_inr", 2.0)),
        baseline_forecast_units=float(gap["evidence"].get("projected_sellthrough") or 0.0),
        markdown_elasticity=ctx.tenant.elasticity_for(product.category),
        days_left=float((date.fromisoformat(str(gap["deadline_date"])) - ctx.as_of).days),
        markdown_ramp_days=float(ctx.tenant.markdown_setting("ramp_days", 0) or 0),
        bundle_partner_unit_cost=float(partner.get("unit_cost") or 0.0), bundle_partner_list_price=float(partner.get("list_price") or 0.0),
    )


def _guardrail_context(ctx: PlannerContext, draft: dict[str, Any]) -> gr.GuardrailContext:
    sku = draft["target"]["sku"]
    node_ids = draft["target"]["node_ids"]
    product = _product(ctx, sku)
    params = draft.get("mechanic_params") or {}
    partner = ctx.products.get(params.get("bundle_sku") or "", {})
    # The audience the gate sees is the same filtered list Approve will assign from
    # (eligible_audience), always on web_chat consent: an outlet-channel draft is not exempt from
    # the frequency-cap and subscription checks, and no longer sees an empty outlet consent table.
    # Consequence, stated plainly: rule_consent_required / rule_frequency_cap /
    # rule_subscription_protect verify that this filter step ran correctly -- they do not screen a
    # raw, unfiltered candidate audience. See
    # tests/unit/test_guardrails.py::test_consent_frequency_subscription_rules_can_genuinely_fail
    # for proof each rule's own logic can reject a violating audience when one is given.
    _, filtered = eligible_audience(ctx, draft)
    consented = _consented(ctx, "web_chat")
    recent = _recent_play_counts(ctx)
    subscribers = frozenset(c["customer_id"] for c in ctx.store.read("customers") if sku in (c.get("subscription_skus") or []))
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

    gap_evidence = (_gap(ctx, draft["gap_id"]).get("evidence") or {}) if draft.get("gap_id") else {}
    catalogue_names = {p["name"] for p in ctx.products.values()}
    # P3: free-text strings of the gap evidence (store notes, cached results) are untrusted; a string that is
    # exactly a catalogue product name (the evidence carries substitute names) is the product's canonical name.
    untrusted = tuple(t for t in strings_in(gap_evidence) if t not in catalogue_names)
    return gr.GuardrailContext(
        untrusted_texts=untrusted,
        product=product, tenant=ctx.tenant, audience_customer_ids=filtered, recent_plays_count=recent, consented_customer_ids=consented,
        subscribers_for_sku=subscribers, stockout_gap_skus_at_node=stockout, resolve_citation=resolve,
        bundle_partner_unit_cost=float(partner.get("unit_cost") or 0.0), bundle_partner_list_price=float(partner.get("list_price") or 0.0),
        as_of=ctx.as_of,
    )


# ----------------------------------------------------------------------------- tools

def get_gap(gap_id: str) -> dict:
    """Return the gap row (type, sku, node, units at risk, deadline, rupees at stake, evidence)."""
    ctx = current()
    g = dict(_gap(ctx, gap_id))
    p = ctx.products.get(g["sku"], {})
    # P3: free text that reaches the model through this tool is cleaned in code first (length, control
    # characters, instruction-like text replaced by the SKU id); real catalogue names and ids pass unchanged.
    g["evidence"] = clean_tree(g.get("evidence") or {}, g["sku"])
    g["product"] = {"name": clean_text(p["name"], g["sku"]) if p.get("name") else None, "category": p.get("category"), "unit_cost": p.get("unit_cost"), "list_price": p.get("list_price"), "margin_floor_pct": ctx.tenant.margin_floor(p.get("category", "default")), "shelf_life_days": p.get("shelf_life_days")}
    g["node"] = {k: ctx.nodes.get(g["node_id"], {}).get(k) for k in ("name", "type", "cluster_id", "lead_time_days")}
    g["node"]["name"] = clean_text(g["node"]["name"], g["node_id"]) if g["node"]["name"] else None
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
            out.append({"sku": psku, "name": clean_text(p["name"], psku), "list_price": float(p["list_price"]), "unit_cost": float(p["unit_cost"]), "qty_on_hand": stock[psku]})
    base = float(ctx.products[sku]["list_price"])
    out.sort(key=lambda r: (abs(r["list_price"] - base), -r["qty_on_hand"], r["sku"]))
    return out[:3]


def _transfer_candidates(ctx: PlannerContext, node_id: str) -> list[dict]:
    """Outlets in the same cluster (physical sale is allowed until expiry)."""
    cluster = ctx.nodes.get(node_id, {}).get("cluster_id")
    return [{"node_id": n["node_id"], "name": clean_text(n["name"], n["node_id"])} for n in ctx.nodes.values() if n["type"] == "outlet" and n["cluster_id"] == cluster]


def get_candidate_audiences(sku: str, node_ids: list[str], objective: str, gap_id: str | None = None) -> list[dict]:
    """Segments reachable for this sku at these nodes: size before and after the consent filter, mean affinity.

    Pass `gap_id` when it is available (get_gap's response) so a gap whose evidence carries
    `requesting_customer_ids` -- assortment_gap, sourced from real customer asks with no coverage
    in the grocery affinity table -- still reaches its real, demonstrated audience instead of an
    empty one."""
    ctx = current()
    requesting: list[str] | None = None
    if gap_id:
        try:
            requesting = (_gap(ctx, gap_id).get("evidence") or {}).get("requesting_customer_ids")
        except KeyError:
            requesting = None
    ids = audience_customer_ids(ctx, sku, node_ids, requesting_customer_ids=requesting)
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
        out.append({"segment_id": seg, "name": clean_text(names.get(seg, seg), seg), "size_before_consent": v["before"], "size_after_consent": v["after"], "mean_affinity": round(sum(v["aff"]) / len(v["aff"]), 3) if v["aff"] else 0.0})
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
    "mechanic": "bundle | usual_order_addon | substitution | preorder | subscription_nudge | coupon | outlet_markdown | transfer_plus_nudge | markdown",
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
    if draft.get("mechanic") == MARKDOWN_MECHANIC:
        pct = (draft.get("mechanic_params") or {}).get("markdown_pct")
        if not isinstance(pct, int | float) or isinstance(pct, bool) or not 0 < pct <= 100:
            problems.append("mechanic_params.markdown_pct is required for a markdown (0 to 100)")
    elif not isinstance(audience, dict):
        problems.append("audience is required (object with segment_ids, size_before_consent, size_after_consent)")
    elif not audience.get("segment_ids"):
        problems.append("audience.segment_ids is required")
    return problems


def _draft_error(problems: list[str]) -> dict:
    return {"error": "play_draft is incomplete: " + "; ".join(problems), "required_shape": DRAFT_SHAPE}


def _markdown_reference(ctx: PlannerContext, draft: dict[str, Any]) -> dict[str, Any]:
    """The best site-wide markdown at the tenant's depths, from the same demand model, in the shape of
    `alternatives`: the model sees what a plain price cut recovers before it proposes anything, and the
    beats_markdown check will hold the proposal to it. {} when the lot is past its online sell-by, the node is
    an outlet (outlet_markdown is the lever there) or no depth clears the margin floor."""
    gap = _gap(ctx, draft["gap_id"])
    if _markdown_blocked(ctx, gap):
        return {}
    gctx = _guardrail_context(ctx, draft)
    est_ctx = _estimator_context(ctx, draft)
    floor = gr.clearance_floor({"mechanic": MARKDOWN_MECHANIC, "target": {"deadline_date": gap["deadline_date"]}}, gctx)
    best = best_markdown(est_ctx, gr.markdown_depths(ctx.tenant), floor_pct=floor if (floor is not None and floor < gctx.product.margin_floor_pct) else None, end_date=gap["deadline_date"])
    if best is None:
        return {}
    alt = {"mechanic": MARKDOWN_MECHANIC, "mechanic_params": {"markdown_pct": best["markdown_pct"], "end_date": gap["deadline_date"]}, "expected_units": best["units"], "expected_margin_inr": best["margin_inr"],
           "rejected_because": f"reference only: the best plain markdown ({best['markdown_pct']:g}% off, same demand model) recovers INR {best['recovery_inr']:.2f} versus doing nothing; a proposal that recovers more than {gr.beats_markdown_tolerance(ctx.tenant, best['recovery_inr']):.2f} less is rejected"}
    return {"alternatives": [alt], "best_markdown_recovery_inr": best["recovery_inr"]}


def _markdown_blocked(ctx: PlannerContext, gap: dict[str, Any]) -> bool:
    sellby_passed = bool(gap["evidence"].get("sellby_passed")) or (gap["deadline_type"] == "online_sellby" and gap["deadline_date"] < ctx.as_of.isoformat())
    return sellby_passed or ctx.nodes.get(gap["node_id"], {}).get("type") == "outlet"


def _estimate_one(ctx: PlannerContext, play_draft: dict) -> dict:
    problems = _draft_problems(play_draft)
    if problems:
        return _draft_error(problems)
    try:
        draft = copy.deepcopy(play_draft)
        apply_derived_audience(ctx, draft)  # the model's own audience figure is never trusted
        out = estimate(draft, _estimator_context(ctx, draft))
        # what the estimate was computed on, so the model sees the real audience, not its own guess
        out["audience"] = {"size_before_consent": draft["audience"]["size_before_consent"], "size_after_consent": draft["audience"]["size_after_consent"]}
        out["channel"] = draft["channel"]
        out.update(_markdown_reference(ctx, draft))
        return out
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
        draft = copy.deepcopy(play_draft)
        apply_derived_audience(ctx, draft)
        gctx = _guardrail_context(ctx, draft)
        out = gr.check(draft, gctx)
        if ctx.tenant.markdown_setting("beats_markdown", True) and not _beats_markdown_exempt(draft):
            gap = _gap(ctx, draft["gap_id"])
            ectx = _estimator_context(ctx, draft)
            bm = gr.check_beats_markdown(draft, estimate(draft, ectx), gctx, ectx, sellby_passed=_markdown_blocked(ctx, gap) or bool(gap["evidence"].get("sellby_passed")))
            # a gate check beside the eight rules: propose_play rejects on it, so the model should see it here
            out["beats_markdown"] = {"passed": bm["passed"], "detail": bm["detail"]}
            out["gate_passed"] = bool(out["all_passed"] and bm["passed"])
        return out
    except KeyError as e:
        return {"error": f"check_guardrails: unknown reference {e}", "required_shape": DRAFT_SHAPE}


def play_row(ctx: PlannerContext, play: dict[str, Any]) -> dict[str, Any]:
    """The `plays` table row for a play: the denormalised scalar columns (docs/DATA_MODEL.md's
    `plays` table) plus the full object as `play_json`. Shared by `propose_play` (the first write,
    below) and run.py (the re-upsert once a run's `source` is known, after propose_play already
    returned) so the column list is never duplicated between the two writers."""
    return {
        "tenant_id": ctx.tenant.tenant_id, "play_id": play["play_id"], "gap_id": play["gap_id"], "status": play["status"], "objective": play["objective"],
        "mechanic": play["mechanic"], "channel": play["channel"], "sku": play["target"]["sku"], "target_node_ids": play["target"]["node_ids"],
        "target_batch_ids": play["target"]["batch_ids"], "window_start": play["window"]["start"], "window_end": play["window"]["end"],
        "policy_version": play["policy_version"], "created_at": play["created_at"], "approved_at": play.get("approved_at"), "play_json": json.dumps(play, ensure_ascii=False),
    }


def _beats_markdown_exempt(play: dict[str, Any]) -> bool:
    """Plays that are not a way to clear an at-risk lot (stockout prevention and the like) are not compared with a
    price cut; neither is a play whose objective the markdown does not serve."""
    return play.get("objective") not in ("clear_online_sellby", "clear_expiry")


def propose_play(play: dict, tool_context: ToolContext) -> dict:
    """Validate the play against the JSON Schema and the gate, write it, and end the planning loop."""
    ctx = current()
    if isinstance(play, dict):
        # A live model often names the identifier `id` (every recorded run did, on attempt 1) instead
        # of the schema's `play_id`: accept the alias and drop the duplicate rather than burn an attempt.
        if "id" in play:
            alias = play.pop("id")
            if not play.get("play_id") and isinstance(alias, str):
                play["play_id"] = alias
        # Server-owned fields. A live model will otherwise invent them: the first Vertex run wrote
        # created_at "2023-10-27" and copied the Sense run id into trace_ref.
        pinned = os.environ.get("TAAL_NOW")
        now = datetime.fromisoformat(pinned.replace("Z", "+00:00")).astimezone(UTC) if pinned else datetime.now(UTC)
        play["created_at"] = now.isoformat(timespec="seconds").replace("+00:00", "Z")
        play["status"] = "proposed"
        play["policy_version"] = ctx.policy_version
        if ctx.play_id:
            play["play_id"] = ctx.play_id
        if isinstance(play.get("holdout"), dict) and play.get("play_id"):
            play["holdout"]["seed"] = f"seed-{play['play_id']}"  # from the final id, never the model's text
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
        try:
            rederive_play(ctx, play)
        except KeyError as e:
            errors.append(f"unknown reference {e}")
    if not errors:
        gap = _gap(ctx, play["gap_id"])
        sellby_passed = bool(gap["evidence"].get("sellby_passed")) or (gap["deadline_type"] == "online_sellby" and gap["deadline_date"] < ctx.as_of.isoformat())
        if sellby_passed and play["mechanic"] in ONLINE_ONLY_BLOCKED:
            errors.append("target lot is past its online sell-by: only outlet_markdown or transfer_plus_nudge are allowed")
        if play["mechanic"] == MARKDOWN_MECHANIC and ctx.nodes.get(gap["node_id"], {}).get("type") == "outlet":
            errors.append("markdown is an online price cut; at an outlet use outlet_markdown")
        gctx = _guardrail_context(ctx, play)
        check = gr.check(play, gctx)
        if ctx.tenant.markdown_setting("beats_markdown", True) and not _beats_markdown_exempt(play):
            bm = gr.check_beats_markdown(play, {"counterfactuals": play["counterfactuals"], "expected_outcome": play["expected_outcome"]}, gctx, _estimator_context(ctx, play), sellby_passed=sellby_passed or _markdown_blocked(ctx, gap))
            if not bm["passed"]:
                errors.append(f"beats_markdown: {bm['detail']}")
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
                baseline_units=baseline_units_of(_estimator_context(ctx, play)) if play["mechanic"] == MARKDOWN_MECHANIC else 0.0,
            )
            if mismatches:
                errors.extend(f"runtime invariant: {m}" for m in mismatches)
    if errors:
        tool_context.state["guardrails_all_passed"] = False
        return {"play_id": None, "valid": False, "errors": errors}
    play["cost"] = governor.cost_for_play(play, _gap(ctx, play["gap_id"]), ctx.tenant)
    ctx.store.upsert("plays", "play_id", play_row(ctx, play))
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
