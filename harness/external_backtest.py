"""Run Taal's own backtest (jobs.sense.backtest.run_backtest, unchanged) and gap detector on the
committed Online Retail II sample (data/external/online_retail_ii) and write summary numbers only.

    uv run python -m harness.external_backtest [--sample DIR] [--date YYYY-MM-DD]
    -> eval/raw/external_backtest_<date>.json

The gap detector needs on-hand stock (and, for four of its types, an expiry date); the dataset has
neither, so it runs on an empty inventory and reports what it finds (0), plus which inputs are missing.
"""
from __future__ import annotations

import argparse
import json
import statistics
import tempfile
from collections import Counter, defaultdict
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from agents.gate.config import load_tenant
from agents.gate.store import LocalStore
from data.external.online_retail_ii.load import ABSENT, sample_to_tables
from jobs.sense.backtest import HORIZON, MAX_ORIGINS, run_backtest
from jobs.sense.forecast import SeriesModel, forecast
from jobs.sense.gaps import detect

ROOT = Path(__file__).resolve().parent.parent
GAP_TYPES = ("online_sellby_breach", "expiry_writeoff", "stockout_risk", "rebalance", "slow_mover", "unmet_demand")


def _means(rows: list[dict]) -> dict:
    w = sum(r["n_series"] for r in rows)
    return {
        "mean_mape": round(sum(r["mape"] for r in rows) / len(rows), 4),
        "mean_bias": round(sum(r["bias"] for r in rows) / len(rows), 4),
        "series_weighted_mape": round(sum(r["mape"] * r["n_series"] for r in rows) / w, 4),
    }


def distribution(sales: list[dict], origins: list[str]) -> dict:
    """Same slots and model as run_backtest, re-walked only to show the spread behind the mean: the
    pooled mean must equal the mean of the per-origin MAPEs run_backtest wrote (checked by the caller)."""
    hist: dict[str, dict[date, float]] = defaultdict(lambda: defaultdict(float))
    for s in sales:
        hist[s["sku"]][date.fromisoformat(s["date"])] += s["units"]
    ape, act, pred, per_origin = [], [], [], []
    for o in origins:
        origin = date.fromisoformat(o)
        mine = []
        for series in hist.values():
            m = SeriesModel({d: (u, False) for d, u in series.items() if d < origin}, origin)
            for i in range(HORIZON):
                d = origin + timedelta(days=i)
                if series.get(d, 0) > 0:
                    p = m.p50(d, on_promo=False, is_festival=False)
                    mine.append(abs(p - series[d]) / series[d])
                    act.append(series[d])
                    pred.append(p)
        per_origin.append(sum(mine) / len(mine))
        ape += mine
    return {"scored_series_days": len(ape), "mean_ape_rewalk": round(sum(per_origin) / len(per_origin), 4), "median_ape": round(statistics.median(ape), 3),
            "share_ape_over_100pct": round(sum(1 for x in ape if x > 1) / len(ape), 3),
            "mean_actual_units": round(statistics.mean(act), 1), "mean_forecast_units": round(statistics.mean(pred), 1)}


def run(sample: Path, day: str) -> dict:
    tables = sample_to_tables(sample)
    with tempfile.TemporaryDirectory() as tmp:
        store = LocalStore(tmp)
        for t, rows in tables.items():
            store.write(t, rows)
        rows = run_backtest(store, f"external_backtest_{day}", datetime.now(UTC).isoformat(timespec="seconds"))
        last = date.fromisoformat(max(s["date"] for s in tables["sales_daily"]))
        as_of = last + timedelta(days=1)
        fc = forecast(store, as_of, "external")
        by_series = {(r["sku"], r["cluster_id"]): r["method"] for r in fc}
        method = Counter(by_series.values())
        gaps = detect(store, fc, as_of, load_tenant(), "external")
    # Share of (sku, horizon-day) slots with a sale, over the backtest windows: the metric only scores those.
    sales = Counter((s["sku"], s["date"]) for s in tables["sales_daily"])
    skus = {p["sku"] for p in tables["products"]}
    origins = sorted({r["origin_date"] for r in rows})
    slots = [(sku, (date.fromisoformat(o) + timedelta(days=i)).isoformat()) for o in origins for sku in skus for i in range(HORIZON)]
    dist = distribution(tables["sales_daily"], origins)
    assert abs(dist["mean_ape_rewalk"] - _means(rows)["mean_mape"]) < 1e-3, "re-walk disagrees with run_backtest"
    return {
        "dataset": "UCI Online Retail II (CC BY 4.0), top 300 SKUs by units, node = country, one cluster",
        "forecaster": "jobs.sense.forecast.SeriesModel (local_seasonal_xreg), unchanged",
        "metric": "jobs.sense.backtest.run_backtest: rolling origin, 7-day horizon, MAPE over days with actual > 0",
        "series": len(skus), "sales_rows": len(tables["sales_daily"]), "nodes": len(tables["nodes"]),
        "history": {"first": min(s["date"] for s in tables["sales_daily"]), "last": last.isoformat()},
        "origins": origins, "n_origins": len(origins), "max_origins": MAX_ORIGINS,
        "per_origin": [{"origin": r["origin_date"], "mape": r["mape"], "bias": r["bias"], "n_series": r["n_series"]} for r in sorted(rows, key=lambda r: r["origin_date"])],
        **_means(rows),
        "spread_behind_the_mean": dist,
        "share_of_series_days_with_a_sale_in_windows": round(sum(1 for s in slots if s in sales) / len(slots), 3),
        "forecast_method_counts": dict(method),
        "gap_detector": {"as_of": as_of.isoformat(), "inventory_batches": 0, "gaps_total": len(gaps),
                         "gaps_by_type": {t: sum(1 for g in gaps if g["type"] == t) for t in GAP_TYPES},
                         "not_computable": "every gap type needs on-hand stock; the first four also need expiry or sell-by dates",
                         "absent_fields": ABSENT},
    }


def synthetic_reference() -> dict:
    rows = [json.loads(x) for x in open(ROOT / "eval/raw/backtest_rows_2026-09-20.jsonl", encoding="utf-8") if x.strip()]
    return {"source": "eval/raw/backtest_rows_2026-09-20.jsonl", "n_rows": len(rows), **_means(rows)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sample", type=Path, default=ROOT / "data/external/online_retail_ii/sample")
    ap.add_argument("--date", default=date.today().isoformat())
    a = ap.parse_args(argv)
    out = run(a.sample, a.date) | {"synthetic_reference": synthetic_reference()}
    path = ROOT / "eval/raw" / f"external_backtest_{a.date}.json"
    path.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: out[k] for k in ("mean_mape", "mean_bias", "series_weighted_mape", "n_origins", "forecast_method_counts", "gap_detector")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
