"""Measure job (DECISIONS §5.7): treated vs holdout per play inside the play window.

    python -m jobs.measure [--data .local/data]

responders   = customers in the arm with an order line carrying play_id, or the target sku at a
               target node, inside [window.start, window.end]
lift         = treated response rate - holdout response rate
CI           = normal approximation, 95%: lift +- 1.96 * sqrt(p_t(1-p_t)/n_t + p_h(1-p_h)/n_h)
status       = measured only if treated customers >= holdout.min_treated_n AND holdout customers >= 1;
               otherwise unmeasured and no lift/CI is written (§17.5: a lift without a holdout fails the job)
priors       = Beta-Binomial update with exact treated responder / non-responder counts
waste line   = units_target_lot x pack_weight_g / 1000 x EMISSIONS_FACTOR, labelled an estimate
CEO number   = (treated margin - holdout margin scaled to treated size) / treated discount cost
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agents.gate.config import load_tenant
from agents.gate.estimator import update_prior
from agents.gate.store import LocalStore, load_catalogue

# kg CO2e per kg of food wasted, an estimate for the "Most Impactful" line only; the source and its
# caveats are in docs/DATA_MODEL.md. Replace with a tenant-specific factor when one exists.
EMISSIONS_FACTOR_KGCO2E_PER_KG = 2.5
Z95 = 1.959964


class MeasureError(RuntimeError):
    pass


def _rate(responders: int, customers: int) -> float:
    return responders / customers if customers else 0.0


def measure_play(play: dict[str, Any], assignments: list[dict[str, Any]], lines: list[dict[str, Any]], product: dict[str, Any], computed_at: str) -> list[dict[str, Any]]:
    """Two play_outcomes rows (treated, holdout) for one play."""
    arms: dict[str, set[str]] = {"treated": set(), "holdout": set()}
    for a in assignments:
        arms[a["arm"]].add(a["customer_id"])
    if not arms["holdout"] and (arms["treated"]):
        raise MeasureError(f"{play['play_id']}: no holdout arm; refusing to compute a lift")
    w0, w1 = play["window"]["start"], play["window"]["end"]
    sku, nodes = play["target"]["sku"], set(play["target"]["node_ids"])
    unit_cost = float(product["unit_cost"])
    per_arm: dict[str, dict[str, Any]] = {arm: {"responders": set(), "units": 0, "revenue": 0.0, "margin": 0.0, "discount": 0.0} for arm in arms}
    for ln in lines:
        if not (w0 <= ln["ts"] <= w1):
            continue
        cid = ln["customer_id"]
        arm = "treated" if cid in arms["treated"] else ("holdout" if cid in arms["holdout"] else None)
        if arm is None:
            continue
        hit = ln.get("play_id") == play["play_id"] or (ln["sku"] == sku and ln.get("node_id") in nodes)
        if not hit:
            continue
        acc = per_arm[arm]
        acc["responders"].add(cid)
        qty = int(ln["qty"])
        price, disc = float(ln["price"]), float(ln.get("discount") or 0.0)
        acc["units"] += qty
        acc["revenue"] += qty * (price - disc)
        acc["margin"] += qty * (price - disc - unit_cost)
        acc["discount"] += qty * disc
    n_t, n_h = len(arms["treated"]), len(arms["holdout"])
    r_t, r_h = len(per_arm["treated"]["responders"]), len(per_arm["holdout"]["responders"])
    min_treated = int(play["holdout"]["min_treated_n"])
    measurable = n_t >= min_treated and n_h >= 1
    p_t, p_h = _rate(r_t, n_t), _rate(r_h, n_h)
    lift = ci_low = ci_high = None
    if measurable:
        lift = p_t - p_h
        se = math.sqrt(p_t * (1 - p_t) / n_t + p_h * (1 - p_h) / n_h)
        ci_low, ci_high = lift - Z95 * se, lift + Z95 * se
    units_at_risk = int(play["target"]["units"])
    rows = []
    for arm in ("treated", "holdout"):
        acc = per_arm[arm]
        units = int(acc["units"])
        waste_avoided = min(units, units_at_risk) * unit_cost
        kg = min(units, units_at_risk) * float(product.get("pack_weight_g") or 0) / 1000.0
        scaled_holdout_margin = per_arm["holdout"]["margin"] * (n_t / n_h) if n_h else 0.0
        ceo = None
        if arm == "treated" and measurable and acc["discount"] > 0:
            ceo = (acc["margin"] - scaled_holdout_margin) / acc["discount"]
        rows.append({
            "tenant_id": play.get("tenant_id") or product["tenant_id"], "play_id": play["play_id"], "arm": arm,
            "customers": n_t if arm == "treated" else n_h, "responders": r_t if arm == "treated" else r_h,
            "units_target_lot": units, "revenue": round(acc["revenue"], 2), "margin": round(acc["margin"], 2), "discount_cost": round(acc["discount"], 2),
            "waste_avoided": round(waste_avoided, 2),
            "lift": round(lift, 6) if (measurable and arm == "treated") else None,
            "ci_low": round(ci_low, 6) if (measurable and arm == "treated") else None,
            "ci_high": round(ci_high, 6) if (measurable and arm == "treated") else None,
            "status": "measured" if measurable else "unmeasured", "min_treated_n": min_treated,
            "waste_kg_est": round(kg, 3), "co2e_kg_est": round(kg * EMISSIONS_FACTOR_KGCO2E_PER_KG, 3), "emissions_factor_kgco2e_per_kg": EMISSIONS_FACTOR_KGCO2E_PER_KG,
            "net_margin_per_discount_inr": round(ceo, 4) if ceo is not None else None,
            "computed_at": computed_at,
        })
    return rows


def run_measure(data_dir: str | Path, computed_at: str | None = None) -> dict[str, Any]:
    store = LocalStore(data_dir)
    tenant = load_tenant()
    computed_at = computed_at or datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    products = load_catalogue(store)
    plays = [json.loads(r["play_json"]) if isinstance(r.get("play_json"), str) else (r.get("play_json") or r) for r in store.read("plays")]
    plays = [p for p in plays if p.get("status") in ("approved", "running", "measured", "unmeasured")]
    assignments: dict[str, list[dict]] = defaultdict(list)
    for a in store.read("play_assignments"):
        assignments[a["play_id"]].append(a)
    lines = store.read("order_lines")
    outcomes: list[dict[str, Any]] = []
    priors = {(r["mechanic"], r["category"], r["segment_id"]): r for r in store.read("estimator_priors")}
    skipped: list[str] = []
    for play in plays:
        product = products[play["target"]["sku"]]
        try:
            rows = measure_play(play, assignments.get(play["play_id"], []), lines, product, computed_at)
        except MeasureError:
            # A single play's degenerate assignment (e.g. a small audience whose holdout fraction
            # happened to hash zero customers into the holdout arm -- more likely for a small,
            # precisely-targeted play than a broad one) must not take down measurement for every
            # other play in the tenant. Left unmeasured this run; a future re-assignment or a
            # bigger audience next time fixes it.
            skipped.append(play["play_id"])
            continue
        outcomes.extend(rows)
        treated = rows[0]
        if treated["status"] == "measured":
            key = (play["mechanic"], product["category"], "*")
            prior = priors.get(key) or {"tenant_id": tenant.tenant_id, "mechanic": play["mechanic"], "category": product["category"], "segment_id": "*", "alpha": 1.0, "beta": 19.0, "n_measured": 0}
            alpha, beta = update_prior(float(prior["alpha"]), float(prior["beta"]), treated["responders"], treated["customers"] - treated["responders"])
            prior.update({"alpha": alpha, "beta": beta, "n_measured": int(prior["n_measured"]) + treated["customers"], "updated_at": computed_at})
            priors[key] = prior
    # replace outcomes for measured plays; keep older rows for other plays
    keep = [r for r in store.read("play_outcomes") if r["play_id"] not in {p["play_id"] for p in plays}]
    store.write("play_outcomes", keep + outcomes)
    store.write("estimator_priors", list(priors.values()))
    # status back onto plays
    status_by = {r["play_id"]: r["status"] for r in outcomes if r["arm"] == "treated"}
    rows = store.read("plays")
    for r in rows:
        if r["play_id"] in status_by:
            r["status"] = status_by[r["play_id"]]
            pj = json.loads(r["play_json"]) if isinstance(r.get("play_json"), str) else r.get("play_json")
            if pj:
                pj["status"] = status_by[r["play_id"]]
                r["play_json"] = json.dumps(pj, ensure_ascii=False)
    store.write("plays", rows)
    return {"plays": len(plays), "measured": sum(1 for s in status_by.values() if s == "measured"), "unmeasured": sum(1 for s in status_by.values() if s == "unmeasured"), "skipped": skipped, "computed_at": computed_at}


def main(argv: list[str] | None = None) -> int:
    import os
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", default=None)
    args = ap.parse_args(argv)
    print(json.dumps(run_measure(args.data or os.environ.get("TAAL_DATA_DIR", ".local/data"))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
