"""python -m data.ingest --products ... --batches ... --sales ... --tenant config/tenant.<name>.toml --out .local/data-<name>

Validates the three contract CSVs (plus optional nodes.csv / inbound.csv), derives each batch's
online sell-by date under the tenant's rule, writes the LocalStore tenant, runs Sense on it and
prints what Taal would have flagged. Local only: nothing is sent anywhere.
Exit codes: 0 ok, 2 contract violation (every problem is printed), 3 --out already holds a store.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from agents.gate.config import load_tenant

from .contract import ContractError
from .ingest import (
    build_tables,
    default_as_of,
    force_local_backends,
    load_and_validate,
    render,
    summarise,
    write_store,
)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m data.ingest", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--products", required=True, help="products.csv")
    ap.add_argument("--batches", required=True, help="inventory_batches.csv (online_sellby_date is derived, never supplied)")
    ap.add_argument("--sales", required=True, help="sales.csv (daily units per sku x node)")
    ap.add_argument("--tenant", required=True, help="config/tenant.<name>.toml: tenant_id, sell-by rule, thresholds, margin floors")
    ap.add_argument("--out", required=True, help="new directory for the LocalStore tenant, e.g. .local/data-<name>")
    ap.add_argument("--nodes", default=None, help="optional nodes.csv (node_id,type,lead_time_days,cluster_id[,lat,lng])")
    ap.add_argument("--inbound", default=None, help="optional inbound.csv (po_id,sku,node_id,qty,eta)")
    ap.add_argument("--as-of", default=None, help="first forecast day (default: the day after the last sales date)")
    ap.add_argument("--default-lead-time-days", type=int, default=3, help="lead time for every node when --nodes is not given")
    ap.add_argument("--json", action="store_true", help="print the summary as JSON instead of text")
    args = ap.parse_args(argv)

    overridden = force_local_backends()
    tenant = load_tenant(args.tenant)
    try:
        inputs = load_and_validate(args.products, args.batches, args.sales, args.nodes, args.inbound)
    except ContractError as e:
        print(f"ingest: {len(e.problems)} contract problem(s); nothing was written", file=sys.stderr)
        for p in e.problems:
            print(f"  {p}", file=sys.stderr)
        return 2
    as_of = date.fromisoformat(args.as_of) if args.as_of else default_as_of(inputs)
    tables = build_tables(inputs, tenant, as_of, args.default_lead_time_days)
    try:
        store = write_store(args.out, tables, tenant, as_of, inputs, args.tenant)
    except FileExistsError as e:
        print(f"ingest: {e}", file=sys.stderr)
        return 3

    from jobs.sense.run import run_sense

    record = run_sense(store.root, as_of, tenant=tenant)
    summary = summarise(store, as_of, tenant.sellby_rule.version)
    summary["sense_run"] = {k: record[k] for k in ("run_id", "forecast_rows", "series", "gaps", "timing_ms")}
    summary["warnings"] = inputs.warnings + [f"{k}={v} ignored: ingest always runs locally" for k, v in overridden.items()]
    (Path(store.root) / "ingest_report.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True))
    else:
        print(f"Ingested {len(inputs.products)} products, {len(inputs.batches)} batches, {len(inputs.sales)} sales rows into {store.root} (tenant {tenant.tenant_id})")
        for w in summary["warnings"]:
            print(f"warning: {w}")
        print()
        print(render(summary, tenant.currency))
        print(f"\nFull report: {Path(store.root) / 'ingest_report.json'}; gaps: {Path(store.root) / 'gaps.jsonl'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
