"""Sense job entrypoint: forecasts -> gaps -> segments -> substitutes -> style trends -> run record.

    python -m jobs.sense [--data .local/data] [--as-of 2026-09-12]

Locally this runs the pure-Python forecaster against the JSONL store; on Google Cloud the same
steps are the SQL files under data/bigquery/sense executed by a Cloud Run Job (infra/).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any

from agents.gate.config import load_tenant
from agents.gate.store import LocalStore

from .forecast import forecast, run_id_for
from .gaps import detect
from .segments import build_segments, build_substitutes
from .trends import build_style_trends


def run_sense(data_dir: str | Path, as_of: date | None = None) -> dict[str, Any]:
    store = LocalStore(data_dir)
    manifest = json.loads((store.root / "manifest.json").read_text(encoding="utf-8")) if (store.root / "manifest.json").exists() else {}
    as_of = as_of or date.fromisoformat(manifest.get("as_of", date.today().isoformat()))
    tenant = load_tenant()
    t0 = time.perf_counter()
    run_id = run_id_for(as_of)
    rows = forecast(store, as_of, run_id)
    store.write("forecasts", rows)
    t1 = time.perf_counter()
    gaps = detect(store, rows, as_of, tenant, run_id)
    store.write("gaps", gaps)
    t2 = time.perf_counter()
    segments = build_segments(store, as_of)
    subs = build_substitutes(store)
    t3 = time.perf_counter()
    trends = build_style_trends(store, as_of, tenant, run_id)
    store.write("style_trends", trends)
    t4 = time.perf_counter()
    threshold = float(tenant.thresholds.get("min_rupees_at_stake_for_planner", 500))
    record = {
        "run_id": run_id, "as_of": as_of.isoformat(), "tenant_id": tenant.tenant_id,
        "forecast_rows": len(rows), "series": len({(r["sku"], r["node_id"]) for r in rows}), "gaps": len(gaps),
        "gaps_by_type": {t: sum(1 for g in gaps if g["type"] == t) for t in ("online_sellby_breach", "expiry_writeoff", "stockout_risk", "rebalance", "slow_mover", "unmet_demand", "assortment_gap")},
        "planner_eligible": sum(1 for g in gaps if g["rupees_at_stake"] >= threshold), "planner_threshold_inr": threshold,
        "segments": len(segments), "substitute_rows": len(subs), "style_trends": len(trends),
        "timing_ms": {"forecast": int((t1 - t0) * 1000), "gaps": int((t2 - t1) * 1000), "segments_substitutes": int((t3 - t2) * 1000), "trends": int((t4 - t3) * 1000), "total": int((t4 - t0) * 1000)},
        "model": rows[0]["model"] if rows else None,
    }
    store.append("sense_runs", [record])
    return record


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", default=None)
    ap.add_argument("--as-of", default=None)
    args = ap.parse_args(argv)
    import os
    data = args.data or os.environ.get("TAAL_DATA_DIR", ".local/data")
    rec = run_sense(data, date.fromisoformat(args.as_of) if args.as_of else None)
    print(json.dumps({k: v for k, v in rec.items() if k != "gaps_by_type"} | {"gaps_by_type": rec["gaps_by_type"]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
