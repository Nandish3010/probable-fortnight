"""Show the estimator prior moving, for the flagship play only, on SYNTHETIC orders.

    uv run python -m harness.prior_update_demo                      # writes <TAAL_DATA_DIR>/prior_update_demo.json
    uv run python -m harness.prior_update_demo --raw eval/raw/prior_update_<date>.json

Run once when the tenant is built (`make generate`, infra/Dockerfile.api), so every visitor sees
the same result and "Reset demo data" cannot change it: the API serves the file from the base
data dir, outside any visitor sandbox.

Everything happens in a throwaway OverlayStore over the base tenant, which is never written: the
flagship play stays `proposed` for the Play Desk approve beat, and the base estimator_priors are
not updated, so no other play's estimate moves. What is persisted is only the before -> after of
the one prior this play's measurement would update.

Synthetic orders, all labelled source="synthetic_demo":
- treated arm: response rate = the seeded prior's own mean, alpha / (alpha + beta), read from the
  tenant's estimator_priors row for (mechanic, category, "*") -- consistent with that prior by
  construction; each responder buys one unit of the target sku with the play's bundle discount.
- holdout arm: response rate = the tenant's organic rate for the same sku at the same node over
  the 7 days before the play window (customers in the tenant who bought it / all customers
  homed at that node), computed from the generated order_lines; one unit at list price.
Responders per arm = round(rate x arm size); who responds is a fixed hash order of customer ids,
so the result is deterministic.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from agents.gate.config import load_tenant
from agents.gate.estimator import update_prior
from agents.gate.store import LocalStore, OverlayStore, load_catalogue
from jobs.measure.run import lift_summary, run_measure
from services.api.approve import approve

FLAGSHIP_PLAY_ID = "play_chips_ds07_v1"
APPROVED_AT = datetime(2026, 9, 12, 9, 0, tzinfo=UTC)  # the TAAL_NOW day, same as the committed golden approve
MEASURED_AT = "2026-09-19T00:00:00Z"  # day after the play window closes, same as fixtures/golden_runs/measure_chips.json
OUTPUT_NAME = "prior_update_demo.json"
SOURCE = "synthetic_demo"
TABLES = ("gaps", "plays", "products", "nodes", "customers", "affinity", "consent", "segments", "estimator_priors", "play_assignments", "inventory_batches", "inbound", "order_lines", "play_outcomes", "sense_runs", "policy", "approvals")


def _rank(play_id: str, customer_id: str) -> str:
    return hashlib.sha256(f"{SOURCE}:{play_id}:{customer_id}".encode()).hexdigest()


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds").replace("+00:00", "Z")


def organic_rate(store: LocalStore, sku: str, node_id: str, window_start: str) -> dict[str, Any]:
    start = datetime.fromisoformat(window_start.replace("Z", "+00:00"))
    lo, hi = _iso(start - timedelta(days=7)), _iso(start)
    buyers = {ln["customer_id"] for ln in store.read("order_lines") if ln["sku"] == sku and ln.get("node_id") == node_id and lo <= ln["ts"] < hi}
    homed = [c["customer_id"] for c in store.read("customers") if c["home_node_id"] == node_id]
    return {"rate": len(buyers) / len(homed) if homed else 0.0, "buyers": len(buyers), "customers_at_node": len(homed), "from": lo, "to": hi}


def build(data_dir: str | Path, play_id: str = FLAGSHIP_PLAY_ID) -> dict[str, Any]:
    base = LocalStore(data_dir)
    tenant = load_tenant()
    scratch = Path(tempfile.mkdtemp(prefix="prior_update_demo_"))
    try:
        overlay = OverlayStore(data_dir, scratch)
        for t in TABLES:
            overlay._materialise(t)
        if (Path(data_dir) / "manifest.json").exists():
            (scratch / "manifest.json").write_bytes((Path(data_dir) / "manifest.json").read_bytes())
        approve(overlay, tenant, play_id, APPROVED_AT)
        play = json.loads(overlay.find("plays", play_id=play_id)[-1]["play_json"])
        products = load_catalogue(overlay)
        sku, node_id = play["target"]["sku"], play["target"]["node_ids"][0]
        product = products[sku]
        key = (play["mechanic"], product["category"], "*")
        prior_row = next(r for r in overlay.read("estimator_priors") if (r["mechanic"], r["category"], r["segment_id"]) == key)
        a0, b0 = float(prior_row["alpha"]), float(prior_row["beta"])
        arms: dict[str, list[str]] = {"treated": [], "holdout": []}
        for a in overlay.read("play_assignments"):
            if a["play_id"] == play_id:
                arms[a["arm"]].append(a["customer_id"])
        organic = organic_rate(overlay, sku, node_id, play["window"]["start"])
        rates = {"treated": a0 / (a0 + b0), "holdout": organic["rate"]}
        params = play.get("mechanic_params") or {}
        price = float(product["list_price"])
        bundle_off = 0.0
        if play["mechanic"] == "bundle":
            partner = float(products[params["bundle_sku"]]["list_price"])
            bundle_off = round(max(0.0, price + partner - float(params["bundle_price"])), 2)
        window_start = datetime.fromisoformat(play["window"]["start"].replace("Z", "+00:00"))
        lines: list[dict[str, Any]] = []
        responders: dict[str, int] = {}
        for arm in ("treated", "holdout"):
            k = round(rates[arm] * len(arms[arm]))
            chosen = sorted(arms[arm], key=lambda c: _rank(play_id, c))[:k]
            responders[arm] = len(chosen)
            for i, cid in enumerate(chosen):
                lines.append({
                    "tenant_id": tenant.tenant_id, "order_id": f"SYN-DEMO-{arm[0].upper()}{i:03d}", "line_no": 1, "customer_id": cid, "node_id": node_id,
                    "sku": sku, "qty": 1, "price": price, "discount": bundle_off if arm == "treated" else 0.0,
                    "play_id": play_id if arm == "treated" else None, "ts": _iso(window_start + timedelta(hours=10 + i)), "source": SOURCE,
                })
        overlay.append("order_lines", lines)
        run_measure(overlay.root, computed_at=MEASURED_AT)
        after_row = next(r for r in overlay.read("estimator_priors") if (r["mechanic"], r["category"], r["segment_id"]) == key)
        treated = next(r for r in overlay.read("play_outcomes") if r["play_id"] == play_id and r["arm"] == "treated")
        holdout = next(r for r in overlay.read("play_outcomes") if r["play_id"] == play_id and r["arm"] == "holdout")
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    # the base tenant must be exactly as it was: the flagship play still proposed, priors unmoved
    assert json.loads(base.find("plays", play_id=play_id)[-1]["play_json"])["status"] == "proposed"
    return {
        "play_id": play_id, "mechanic": play["mechanic"], "category": product["category"], "segment_id": "*",
        "data_label": "SYNTHETIC", "orders_source": SOURCE,
        "rates_used": {
            "treated": round(rates["treated"], 6), "treated_basis": f"seeded prior mean alpha/(alpha+beta) = {a0:g}/({a0:g}+{b0:g})",
            "holdout": round(rates["holdout"], 6), "holdout_basis": f"organic 7-day rate for {sku} at {node_id}: {organic['buyers']} buyer(s) / {organic['customers_at_node']} customers homed there, {organic['from']} to {organic['to']}",
        },
        "synthetic_order_lines": len(lines),
        "before": {"alpha": a0, "beta": b0, "n_measured": int(prior_row["n_measured"])},
        "after": {"alpha": float(after_row["alpha"]), "beta": float(after_row["beta"]), "n_measured": int(after_row["n_measured"])},
        "treated_n": int(treated["customers"]), "holdout_n": int(holdout["customers"]),
        "responders": {"treated": int(treated["responders"]), "holdout": int(holdout["responders"])},
        "status": treated["status"], "lift": treated["lift"], **lift_summary(treated["lift"], treated["ci_low"], treated["ci_high"], int(treated["responders"])), "ci": {"low": treated["ci_low"], "high": treated["ci_high"], "level": 0.95, "method": "Newcombe hybrid score (jobs/measure/run.py)"},
        "approved_at": _iso(APPROVED_AT), "measured_at": MEASURED_AT,
        "applied_to_live_estimator": False,
        "note": "Computed by harness.prior_update_demo in a throwaway sandbox; the base tenant's estimator_priors are not changed, so no other play's estimate moves.",
    }


def check(result: dict[str, Any]) -> None:
    """The persisted after must be exactly the conjugate update of before by the treated counts."""
    t = result["responders"]["treated"]
    expected = update_prior(result["before"]["alpha"], result["before"]["beta"], t, result["treated_n"] - t)
    if expected != (result["after"]["alpha"], result["after"]["beta"]):
        raise AssertionError(f"after {result['after']} != update_prior(...) {expected}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default=os.environ.get("TAAL_DATA_DIR", ".local/data"))
    ap.add_argument("--raw", default=None, help="also write the result here (eval/raw/...)")
    args = ap.parse_args(argv)
    result = build(args.data)
    check(result)
    text = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    (Path(args.data) / OUTPUT_NAME).write_text(text, encoding="utf-8")
    if args.raw:
        Path(args.raw).parent.mkdir(parents=True, exist_ok=True)
        Path(args.raw).write_text(text, encoding="utf-8")
    b, a = result["before"], result["after"]
    print(f"prior update ({result['mechanic']} x {result['category']}): Beta({b['alpha']:g},{b['beta']:g}) -> Beta({a['alpha']:g},{a['beta']:g}); "
          f"treated {result['responders']['treated']}/{result['treated_n']}, holdout {result['responders']['holdout']}/{result['holdout_n']}; SYNTHETIC")
    return 0


if __name__ == "__main__":
    sys.exit(main())
