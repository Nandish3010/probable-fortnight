"""Rolling-origin backtest of the local forecaster (DECISIONS §5.2 step 8, §12): refits
`SeriesModel` at each of several historical origins using only data strictly before that origin,
forecasts a short horizon forward, and compares against the sales that actually happened -- the
only way to know whether the forecast is any good, as opposed to just self-consistent.

Origins step back 7 days at a time from the last date the sample slice can still validate (it
needs `horizon` days of real, already-observed sales after the origin to compare against), for as
many steps as the available history supports, capped at `MAX_ORIGINS` (8, per the "8 weeks"
spec) -- the demo tenant's 70-day sample slice does not stretch to a full 8 with a sane lead-in,
and reporting fewer, real origins is more honest than padding to 8 by starving the lead-in.

`tier` groups results by product category (not node type: a cluster mixes dark stores and
outlets, so node type is not a property of a (sku, cluster) series the way category is).
`model` is the `forecasts.model` value being evaluated (locally always `local_seasonal_xreg`;
in production this is where `timesfm` and `arima_xreg` would appear side by side). Writes one
row per (origin, tier, model) to `eval_forecast`.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from typing import Any

from agents.gate.store import LocalStore

from .forecast import MODEL, SeriesModel, _load_history

HORIZON = 7
MAX_ORIGINS = 8
MIN_LEAD_IN_DAYS = 14


def _origins(all_dates: set[date], horizon: int) -> list[date]:
    """Origins that both have >= MIN_LEAD_IN_DAYS of history before them and >= horizon days of
    already-observed actuals after them, stepping back 7 days at a time."""
    if not all_dates:
        return []
    last_actual = max(all_dates)
    first_actual = min(all_dates)
    origins = []
    origin = last_actual - timedelta(days=horizon)
    while origin - timedelta(days=MIN_LEAD_IN_DAYS) >= first_actual and len(origins) < MAX_ORIGINS:
        origins.append(origin)
        origin -= timedelta(days=7)
    return origins


def run_backtest(store: LocalStore, run_id: str, computed_at: str) -> list[dict[str, Any]]:
    nodes = store.read("nodes")
    if not nodes:
        return []
    tenant = nodes[0]["tenant_id"]
    cluster_of = {n["node_id"]: n["cluster_id"] for n in nodes}
    products = {p["sku"]: p for p in store.read("products")}
    hist, _ = _load_history(store, cluster_of)
    all_dates = {d for series in hist.values() for d in series}
    origins = _origins(all_dates, HORIZON)
    rows: list[dict[str, Any]] = []
    for origin in origins:
        # (tier, model) -> list of absolute-percentage-errors and list of signed relative errors
        errors: dict[tuple[str, str], list[float]] = defaultdict(list)
        signed: dict[tuple[str, str], list[float]] = defaultdict(list)
        series_seen: dict[tuple[str, str], set[tuple[str, str]]] = defaultdict(set)
        for (sku, cluster), series in hist.items():
            product = products.get(sku)
            if product is None:
                continue
            tier = product["category"]
            before = {d: v for d, v in series.items() if d < origin}
            model = SeriesModel(before, origin)
            model_name = MODEL
            for i in range(HORIZON):
                d = origin + timedelta(days=i)
                actual = series.get(d, (0.0, False))[0]
                predicted = model.p50(d, on_promo=series.get(d, (0.0, False))[1], is_festival=False)
                if actual > 0:
                    errors[(tier, model_name)].append(abs(predicted - actual) / actual)
                    signed[(tier, model_name)].append((predicted - actual) / actual)
                series_seen[(tier, model_name)].add((sku, cluster))
        for (tier, model_name), ape in errors.items():
            rows.append({
                "tenant_id": tenant, "run_id": run_id, "origin_date": origin.isoformat(), "tier": tier, "model": model_name,
                "mape": round(sum(ape) / len(ape), 4) if ape else None,
                "bias": round(sum(signed[(tier, model_name)]) / len(signed[(tier, model_name)]), 4) if signed[(tier, model_name)] else None,
                "n_series": len(series_seen[(tier, model_name)]), "computed_at": computed_at,
            })
    store.append("eval_forecast", rows)
    return rows


def run_id_for(as_of: date) -> str:
    return f"backtest_{as_of.strftime('%Y%m%d')}_{as_of.isoformat()}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", default=None)
    ap.add_argument("--as-of", default=None)
    args = ap.parse_args(argv)
    data = args.data or os.environ.get("TAAL_DATA_DIR", ".local/data")
    store = LocalStore(data)
    as_of = date.fromisoformat(args.as_of) if args.as_of else date.today()
    computed_at = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    rows = run_backtest(store, run_id_for(as_of), computed_at)
    by_tier_model = sorted({(r["tier"], r["model"]) for r in rows})
    print(json.dumps({
        "rows_written": len(rows), "origins": sorted({r["origin_date"] for r in rows}),
        "tiers_x_models": len(by_tier_model),
        "sample": rows[:3],
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
