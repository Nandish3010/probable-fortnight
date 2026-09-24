"""Portfolio job: plans every planner-eligible gap from the latest Sense run with the same
deterministic drafter/estimator pipeline the Planner falls back to (no model calls, no
credentials; agents/planner/deterministic.py), then aggregates the result into the nightly
portfolio number: total exposure, expected waste avoided and margin across every gap Taal can
draft a play for, the same totals under do-nothing and a blanket markdown, and how many gaps the
Cost Governor triages out before a play is even attempted.

    python -m jobs.portfolio [--data .local/data] [--out eval/raw/portfolio_<date>.json]

`deterministic_plan` drives the same `propose_play` tool a live Planner run does, which writes
each valid play into the `plays` table -- fine for one gap, not for 428 of them landing in the
tenant's real store. So this job runs the whole pass against a throwaway copy of the data
directory (`make generate` / `make sense` must have populated the original first) and discards
the copy when done; the source tenant on disk is never mutated.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from collections import defaultdict
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from agents.gate.config import TenantConfig, load_tenant
from agents.gate.estimator import EstimatorContext, GapFacts, Product
from agents.gate.estimator import counterfactuals as estimator_counterfactuals
from agents.gate.store import LocalStore, load_catalogue
from agents.planner import governor
from agents.planner.context import PlannerContext, reset_context, set_context
from agents.planner.deterministic import deterministic_plan


def _r2(x: float) -> float:
    return round(float(x), 2)


def _gap_counterfactuals(gap: dict[str, Any], product: dict[str, Any], tenant: TenantConfig) -> dict[str, float]:
    """do_nothing/blanket_markdown for a gap with no drafted play, via the same estimator
    function a play's counterfactuals come from (agents/gate/estimator.py::counterfactuals) --
    it only needs the product, the gap's units_at_risk/evidence and the tenant's markdown
    thresholds, none of which depend on a play having been drafted."""
    ectx = EstimatorContext(
        product=Product(
            sku=product.get("sku", gap["sku"]), category=product.get("category", "default"),
            unit_cost=float(product.get("unit_cost") or 0.0), list_price=float(product.get("list_price") or 0.0),
            margin_floor_pct=tenant.margin_floor(product.get("category", "default")),
        ),
        gap=GapFacts(units_at_risk=int(gap["units_at_risk"]), rupees_at_stake=float(gap["rupees_at_stake"]), evidence=gap.get("evidence") or {}),
        audience_size_after_consent=0,
        markdown_elasticity=float(tenant.thresholds.get("markdown_elasticity", 1.0)),
        baseline_forecast_units=float((gap.get("evidence") or {}).get("projected_sellthrough") or 0.0),
    )
    return estimator_counterfactuals({}, ectx)


def run_portfolio(data_dir: str | Path, as_of: str | None = None) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="taal_portfolio_") as scratch:
        shutil.copytree(data_dir, scratch, dirs_exist_ok=True)
        return _run_portfolio_on(scratch, as_of)


def _run_portfolio_on(data_dir: str | Path, as_of: str | None) -> dict[str, Any]:
    store = LocalStore(data_dir)
    tenant = load_tenant()
    products = load_catalogue(store)
    gaps = store.read("gaps")
    sense_run_id = gaps[0]["run_id"] if gaps else None
    as_of = as_of or (json.loads((store.root / "manifest.json").read_text(encoding="utf-8"))["as_of"] if (store.root / "manifest.json").exists() else date.today().isoformat())

    ctx = PlannerContext.build(data_dir, run_id=f"portfolio_{sense_run_id or 'run'}")
    token = set_context(ctx)

    exposure_by_type: dict[str, dict[str, float]] = defaultdict(lambda: {"count": 0, "exposure_inr": 0.0})
    total_exposure = 0.0
    do_nothing_total = 0.0
    blanket_markdown_total = 0.0

    triaged_out = 0
    triaged_out_exposure = 0.0
    triaged_out_reason = None

    eligible_no_play = 0
    eligible_no_play_exposure = 0.0

    planned = 0
    expected_units = 0.0
    expected_margin_inr = 0.0
    expected_waste_avoided_inr = 0.0
    plays: list[dict[str, Any]] = []

    try:
        for gap in gaps:
            rupees = float(gap["rupees_at_stake"])
            total_exposure += rupees
            exposure_by_type[gap["type"]]["count"] += 1
            exposure_by_type[gap["type"]]["exposure_inr"] += rupees

            product = products.get(gap["sku"])
            if product is not None:
                cfs = _gap_counterfactuals(gap, product, tenant)
                do_nothing_total += cfs["do_nothing_inr"]
                blanket_markdown_total += cfs["blanket_markdown_inr"]

            eligible, reason = governor.planner_eligible(gap, tenant)
            if not eligible:
                triaged_out += 1
                triaged_out_exposure += rupees
                triaged_out_reason = triaged_out_reason or reason.split(";")[0].split(" below ")[0] + " below planner threshold"
                continue

            play = deterministic_plan(ctx, gap["gap_id"])
            if play is None:
                eligible_no_play += 1
                eligible_no_play_exposure += rupees
                continue

            planned += 1
            eo = play["expected_outcome"]
            expected_units += eo["units"]
            expected_margin_inr += eo["margin_inr"]
            expected_waste_avoided_inr += eo["waste_avoided_inr"]
            plays.append({
                "gap_id": gap["gap_id"], "play_id": play["play_id"], "type": gap["type"], "sku": gap["sku"], "node_id": gap["node_id"],
                "mechanic": play["mechanic"], "rupees_at_stake": rupees,
                "expected_outcome": eo, "counterfactuals": play["counterfactuals"],
            })
    finally:
        reset_context(token)

    computed_at = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    threshold = float(tenant.thresholds.get("min_rupees_at_stake_for_planner", 500))
    return {
        "sense_run_id": sense_run_id,
        "as_of": as_of,
        "computed_at": computed_at,
        "tenant_id": tenant.tenant_id,
        "totals": {
            "gaps": len(gaps),
            "exposure_inr": _r2(total_exposure),
            "by_type": {t: {"count": v["count"], "exposure_inr": _r2(v["exposure_inr"])} for t, v in sorted(exposure_by_type.items(), key=lambda kv: -kv[1]["exposure_inr"])},
            "do_nothing_inr": _r2(do_nothing_total),
            "blanket_markdown_inr": _r2(blanket_markdown_total),
        },
        "governor": {
            "planner_threshold_inr": threshold,
            "eligible": len(gaps) - triaged_out,
            "triaged_out": triaged_out,
            "triaged_out_exposure_inr": _r2(triaged_out_exposure),
            "triaged_out_reason": triaged_out_reason,
        },
        "planned": {
            "count": planned,
            "eligible_no_play": eligible_no_play,
            "eligible_no_play_exposure_inr": _r2(eligible_no_play_exposure),
            "expected_units": _r2(expected_units),
            "expected_margin_inr": _r2(expected_margin_inr),
            "expected_waste_avoided_inr": _r2(expected_waste_avoided_inr),
        },
        "plays": plays,
    }


def main(argv: list[str] | None = None) -> int:
    import os
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", default=None)
    ap.add_argument("--out", default=None, help="write the full result (including per-play detail) as JSON to this path")
    args = ap.parse_args(argv)
    result = run_portfolio(args.data or os.environ.get("TAAL_DATA_DIR", ".local/data"))
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    summary = {k: v for k, v in result.items() if k != "plays"}
    summary["plays_written"] = len(result["plays"])
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())
