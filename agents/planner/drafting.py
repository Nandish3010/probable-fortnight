"""Draft assembly shared by the stub model and the evalset builder: candidate mechanics in policy
order, the draft Play object, the rationale with every number cited.

The stub model (stub_llm.py) uses these functions to play the Planner's part in CI without a
network. The Vertex-backed Planner writes the same objects itself, guided by prompts/planner.md;
the tools then validate them identically.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

OBJECTIVE_BY_GAP = {
    "online_sellby_breach": "clear_online_sellby", "expiry_writeoff": "clear_expiry", "stockout_risk": "prevent_stockout",
    "rebalance": "rebalance", "slow_mover": "revive_slow_mover", "unmet_demand": "prevent_stockout",
}


def candidate_mechanics(gap: dict[str, Any], policy_text: str) -> list[dict[str, Any]]:
    """Ordered candidates (mechanic + params) for a gap under the policy text. Order encodes the
    policy preferences the Planner is asked to honour; the gate decides what is admissible."""
    p = gap.get("product") or {}
    category = p.get("category")
    policy = policy_text.lower()
    partners = gap.get("bundle_partner_candidates") or []
    outlets = gap.get("transfer_candidates") or []
    inbound_eta = (gap.get("evidence") or {}).get("inbound_eta")
    sellby_passed = bool((gap.get("evidence") or {}).get("sellby_passed"))
    is_outlet = (gap.get("node") or {}).get("type") == "outlet"
    prefer_transfer_tea = "prefer transfers for premium tea" in policy and category == "premium_tea"
    list_price = float(p.get("list_price") or 0)

    def bundle() -> dict[str, Any] | None:
        if not partners:
            return None
        partner = partners[0]
        price = round((list_price + float(partner["list_price"])) * 0.94, 0)
        return {"mechanic": "bundle", "mechanic_params": {"bundle_sku": partner["sku"], "bundle_price": price}}

    def transfer() -> dict[str, Any] | None:
        if not outlets:
            return None
        return {"mechanic": "transfer_plus_nudge", "mechanic_params": {"transfer_to_node": outlets[0]["node_id"], "transfer_units": int(gap["units_at_risk"])}}

    coupon15 = {"mechanic": "coupon", "mechanic_params": {"discount_pct": 15}}
    coupon10 = {"mechanic": "coupon", "mechanic_params": {"discount_pct": 10}}
    markdown10 = {"mechanic": "outlet_markdown", "mechanic_params": {"markdown_pct": 10}}
    addon = {"mechanic": "usual_order_addon", "mechanic_params": {}}
    gtype = gap["type"]
    out: list[dict[str, Any] | None]
    if gtype in ("online_sellby_breach", "expiry_writeoff"):
        if sellby_passed or is_outlet:
            out = [transfer(), markdown10]
        elif prefer_transfer_tea:
            out = [transfer(), coupon10]
        elif "markdowns are the last lever" in policy:
            out = [coupon15, bundle(), transfer(), markdown10]
        else:
            out = [coupon15, coupon10, bundle(), transfer()]
    elif gtype in ("stockout_risk", "unmet_demand"):
        # unmet_demand carries no forecast-derived inbound_eta of its own; a restock PO covers it
        # the same way it would a stockout_risk gap, so the same candidate order applies.
        out = [{"mechanic": "preorder", "mechanic_params": {"preorder_eta_date": inbound_eta}} if inbound_eta else None, {"mechanic": "substitution", "mechanic_params": {}}]
    elif gtype == "rebalance":
        counterpart = (gap.get("evidence") or {}).get("counterpart_node_id")
        out = [{"mechanic": "transfer_plus_nudge", "mechanic_params": {"transfer_to_node": counterpart, "transfer_units": int(gap["units_at_risk"])}} if counterpart else transfer()]
    else:  # slow_mover
        out = [markdown10, transfer()] if is_outlet else [addon, coupon10, transfer()]
    return [c for c in out if c]


def choose_segments(audiences: list[dict[str, Any]], min_size: int = 300) -> list[dict[str, Any]]:
    chosen, total = [], 0
    for a in audiences:
        if a["size_after_consent"] <= 0:
            continue
        chosen.append(a)
        total += a["size_after_consent"]
        if total >= min_size:
            break
    return chosen or audiences[:1]


def build_draft(gap: dict[str, Any], audiences: list[dict[str, Any]], candidate: dict[str, Any], policy_version: str, run_id: str, holdout_fraction: float, min_treated_n: int, languages: list[str], as_of: str) -> dict[str, Any]:
    segs = choose_segments(audiences)
    play_id = f"play_{gap['gap_id'][4:]}_{policy_version}"
    is_outlet = (gap.get("node") or {}).get("type") == "outlet" or candidate["mechanic"] == "outlet_markdown"
    return {
        "play_id": play_id, "gap_id": gap["gap_id"], "tenant_id": gap.get("tenant_id"), "created_at": f"{as_of}T00:00:00Z",
        "objective": OBJECTIVE_BY_GAP[gap["type"]],
        "target": {"sku": gap["sku"], "node_ids": [gap["node_id"]], "batch_ids": [gap["batch_id"]] if gap.get("batch_id") else [], "units": int(gap["units_at_risk"]), "deadline_date": gap["deadline_date"], "deadline_type": gap["deadline_type"]},
        "mechanic": candidate["mechanic"], "mechanic_params": {k: v for k, v in candidate["mechanic_params"].items() if v is not None},
        "audience": {"segment_ids": [s["segment_id"] for s in segs], "filters": {"min_affinity": 0.3}, "purpose": "marketing", "size_before_consent": sum(s["size_before_consent"] for s in segs), "size_after_consent": sum(s["size_after_consent"] for s in segs)},
        "channel": "outlet" if is_outlet else "web_chat",
        "window": {"start": f"{as_of}T00:00:00Z", "end": f"{gap['deadline_date']}T23:59:59Z"},
        "copy": {"language_set": list(languages), "variants": [], "copy_status": "pending"},
        "holdout": {"fraction": holdout_fraction, "seed": f"seed-{play_id}", "min_treated_n": min_treated_n},
        "guardrails": [], "rationale": "", "citations": [], "alternatives": [], "policy_version": policy_version, "trace_ref": f"events/{run_id}", "status": "proposed",
    }


def _sentence_for_policy(policy_text: str, mechanic: str) -> str:
    for line in policy_text.splitlines():
        low = line.lower()
        if mechanic == "transfer_plus_nudge" and "transfer" in low:
            return line.strip()
        if mechanic in ("coupon", "outlet_markdown") and "margin floor" in low:
            return line.strip()
        if mechanic == "bundle" and "bundle" in low:
            return line.strip()
    return next((line.strip() for line in policy_text.splitlines() if line.strip()), "")


def finish_draft(draft: dict[str, Any], gap: dict[str, Any], estimate: dict[str, Any], audiences: list[dict[str, Any]], alternatives: list[dict[str, Any]], policy_text: str) -> dict[str, Any]:
    """Attach estimator output, citations, alternatives and a rationale whose every number is cited."""
    eo, cf = estimate["expected_outcome"], estimate["counterfactuals"]
    d = dict(draft)
    d["expected_outcome"] = eo
    d["counterfactuals"] = cf
    names = {a["segment_id"]: a["name"] for a in audiences}
    seg_names = ", ".join(names.get(s, s) for s in d["audience"]["segment_ids"])
    p = gap.get("product") or {}
    node = (gap.get("node") or {}).get("name") or gap["node_id"]
    deadline_word = {"online_sellby": "online sell-by", "expiry": "expiry", "lead_time": "lead-time"}[gap["deadline_type"]]
    params = d["mechanic_params"]
    how = {
        "bundle": f"a bundle with {params.get('bundle_sku')} at ₹{float(params.get('bundle_price') or 0):.0f}",
        "coupon": f"a {float(params.get('discount_pct') or 0):.0f}% coupon", "outlet_markdown": f"a {float(params.get('markdown_pct') or 0):.0f}% in-store markdown",
        "transfer_plus_nudge": f"a transfer of {int(params.get('transfer_units') or 0)} units to {params.get('transfer_to_node')} with a nudge",
        "preorder": f"a pre-order for the {params.get('preorder_eta_date')} delivery", "substitution": "substitution offers", "usual_order_addon": "a usual-order add-on", "subscription_nudge": "a subscription nudge",
    }[d["mechanic"]]
    rationale = (
        f"{int(gap['units_at_risk'])} units of {p.get('name', gap['sku'])} at {node} are projected unsold before the {deadline_word} deadline on {gap['deadline_date']}; "
        f"doing nothing writes off ₹{cf['do_nothing_inr']:.0f} and a blanket {cf['blanket_markdown_pct']:.0f}% markdown costs ₹{cf['blanket_markdown_inr']:.0f}. "
        f"This play uses {how} for {int(d['audience']['size_after_consent'])} consented customers ({seg_names}): expected {eo['units']:.0f} units, "
        f"margin ₹{eo['margin_inr']:.0f}, discount cost ₹{eo['discount_cost_inr']:.0f}, waste avoided ₹{eo['waste_avoided_inr']:.0f} "
        f"(CI {eo['ci_low']:.0f} to {eo['ci_high']:.0f} units; prior n {eo['prior_n']:.0f}, measured n {int(eo['measured_n'])}). "
        f"Policy {d['policy_version']}: \"{_sentence_for_policy(policy_text, d['mechanic'])}\""
    )
    d["rationale"] = rationale[:2000]
    d["citations"] = [
        {"type": "gap", "ref": gap["gap_id"]}, {"type": "estimator", "ref": eo["estimator_version"]},
        {"type": "policy", "ref": d["policy_version"]}, {"type": "forecast", "ref": gap["evidence"]["forecast_run_id"]},
    ] + ([{"type": "stock", "ref": gap["batch_id"]}] if gap.get("batch_id") else [])
    d["alternatives"] = alternatives[:3]
    return d


def draft_key(candidate: dict[str, Any]) -> str:
    return json.dumps({"mechanic": candidate["mechanic"], "mechanic_params": candidate.get("mechanic_params", {})}, sort_keys=True)


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")
