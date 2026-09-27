"""Sense job entrypoint: forecasts -> gaps -> segments -> substitutes -> style trends -> run record.

    python -m jobs.sense [--data .local/data] [--as-of 2026-09-12]

Locally this runs the pure-Python forecaster against the JSONL store; on Google Cloud the same
steps are the SQL files under data/bigquery/sense executed by a Cloud Run Job (infra/).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from agents.gate.bigquery_store import BigQueryStore
from agents.gate.config import load_tenant
from agents.gate.firestore_cache import build_cache
from agents.gate.store import LocalStore

from .forecast import forecast, run_id_for
from .gaps import detect
from .segments import build_segments, build_substitutes
from .trends import build_style_trends


def build_batch_store(data_dir: str | Path) -> LocalStore:
    """LocalStore (default everywhere) or BigQueryStore, selected by TAAL_BATCH_STORE. Unset or
    'local' never changes behaviour -- the demo tenant's judge-mode serving path is untouched;
    only the taal-sense/taal-measure jobs' own environment sets this to 'bigquery'."""
    backend = os.environ.get("TAAL_BATCH_STORE", "local")
    if backend == "bigquery":
        return BigQueryStore(data_dir)
    if backend != "local":
        raise ValueError(f"TAAL_BATCH_STORE must be 'local' or 'bigquery', got {backend!r}")
    return LocalStore(data_dir)


def run_sense(data_dir: str | Path, as_of: date | None = None) -> dict[str, Any]:
    store = build_batch_store(data_dir)
    manifest_path = store.root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    as_of = as_of or date.fromisoformat(manifest.get("as_of", date.today().isoformat()))
    tenant = load_tenant()
    executed_at = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    execution_name = os.environ.get("CLOUD_RUN_EXECUTION") or os.environ.get("CLOUD_RUN_TASK_INDEX") or "local"
    t0 = time.perf_counter()
    run_id = run_id_for(as_of)
    forecast_backend = os.environ.get("TAAL_FORECAST_BACKEND", "local")
    if forecast_backend == "bigquery_timesfm":
        from .forecast_bigquery import forecast_bigquery

        rows = forecast_bigquery(as_of, run_id, tenant.tenant_id)
    elif forecast_backend == "local":
        rows = forecast(store, as_of, run_id)
    else:
        raise ValueError(f"TAAL_FORECAST_BACKEND must be 'local' or 'bigquery_timesfm', got {forecast_backend!r}")
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
        "executed_at": executed_at, "execution_name": execution_name,
    }
    store.append("sense_runs", [record])
    cache = build_cache(tenant.tenant_id)
    if cache is not None:
        products = {p["sku"]: p for p in store.read("products")}
        record["firestore_mirror"] = {
            "stock_docs": cache.mirror_stock(store.read("inventory_batches"), products, as_of),
            "customer_docs": cache.mirror_customers(store.read("customers"), store.read("consent")),
            "offer_docs": cache.mirror_offers(store.read("offers")),
        }
    return record


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", default=None)
    ap.add_argument("--as-of", default=None)
    args = ap.parse_args(argv)
    data = args.data or os.environ.get("TAAL_DATA_DIR", ".local/data")
    rec = run_sense(data, date.fromisoformat(args.as_of) if args.as_of else None)
    print(json.dumps({k: v for k, v in rec.items() if k != "gaps_by_type"} | {"gaps_by_type": rec["gaps_by_type"]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
