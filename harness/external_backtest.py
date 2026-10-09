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
from data.generator import generate
from jobs.sense.backtest import HORIZON, MAX_ORIGINS, _load_history, _origins, run_backtest
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


def slot_metrics(store: LocalStore) -> dict:
    """Re-walk run_backtest's own slots (same history, origins, SeriesModel, actual > 0 filter) and
    keep every (actual, forecast) pair, to add what the per-origin means hide: pooled WAPE =
    sum|forecast - actual| / sum(actual), and the spread behind MAPE. The (origin, tier) MAPE mean
    from these pairs must equal run_backtest's rows (checked by the caller), so nothing here is a new
    forecast or a different set of slots."""
    nodes = store.read("nodes")
    cluster_of = {n["node_id"]: n["cluster_id"] for n in nodes}
    tier_of = {p["sku"]: p["category"] for p in store.read("products")}
    hist, _ = _load_history(store, cluster_of)
    origins = _origins({d for series in hist.values() for d in series}, HORIZON)
    cells: dict[tuple[date, str], list[float]] = defaultdict(list)
    act, pred = [], []
    for origin in origins:
        for (sku, _cluster), series in hist.items():
            if sku not in tier_of:
                continue
            m = SeriesModel({d: v for d, v in series.items() if d < origin}, origin)
            for i in range(HORIZON):
                d = origin + timedelta(days=i)
                a, promo = series.get(d, (0.0, False))
                if a > 0:
                    p = m.p50(d, on_promo=promo, is_festival=False)
                    cells[(origin, tier_of[sku])].append(abs(p - a) / a)
                    act.append(a)
                    pred.append(p)
    ape = [x for v in cells.values() for x in v]
    return {"scored_series_days": len(act), "mean_ape_rewalk": round(sum(sum(v) / len(v) for v in cells.values()) / len(cells), 4),
            "wape": round(sum(abs(p - a) for p, a in zip(pred, act, strict=True)) / sum(act), 4),
            "median_ape": round(statistics.median(ape), 3), "share_ape_over_100pct": round(sum(1 for x in ape if x > 1) / len(ape), 3),
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
        dist = slot_metrics(store)
    # Share of (sku, horizon-day) slots with a sale, over the backtest windows: the metric only scores those.
    sales = Counter((s["sku"], s["date"]) for s in tables["sales_daily"])
    skus = {p["sku"] for p in tables["products"]}
    origins = sorted({r["origin_date"] for r in rows})
    slots = [(sku, (date.fromisoformat(o) + timedelta(days=i)).isoformat()) for o in origins for sku in skus for i in range(HORIZON)]
    assert abs(dist["mean_ape_rewalk"] - _means(rows)["mean_mape"]) < 1e-3, "re-walk disagrees with run_backtest"
    return {
        "dataset": "UCI Online Retail II (CC BY 4.0), top 300 SKUs by units, node = country, one cluster",
        "forecaster": "jobs.sense.forecast.SeriesModel (local_seasonal_xreg), unchanged",
        "metric": "jobs.sense.backtest.run_backtest: rolling origin, 7-day horizon, MAPE over days with actual > 0; wape = sum|forecast - actual| / sum(actual) over the same scored series-days, pooled",
        "series": len(skus), "sales_rows": len(tables["sales_daily"]), "nodes": len(tables["nodes"]),
        "history": {"first": min(s["date"] for s in tables["sales_daily"]), "last": last.isoformat()},
        "origins": origins, "n_origins": len(origins), "max_origins": MAX_ORIGINS,
        "per_origin": [{"origin": r["origin_date"], "mape": r["mape"], "bias": r["bias"], "n_series": r["n_series"]} for r in sorted(rows, key=lambda r: r["origin_date"])],
        **_means(rows),
        "wape": dist["wape"],
        "spread_behind_the_mean": dist,
        "share_of_series_days_with_a_sale_in_windows": round(sum(1 for s in slots if s in sales) / len(slots), 3),
        "forecast_method_counts": dict(method),
        "gap_detector": {"as_of": as_of.isoformat(), "inventory_batches": 0, "gaps_total": len(gaps),
                         "gaps_by_type": {t: sum(1 for g in gaps if g["type"] == t) for t in GAP_TYPES},
                         "not_computable": "every gap type needs on-hand stock; the first four also need expiry or sell-by dates",
                         "absent_fields": ABSENT},
    }


def synthetic_reference(data_dir: Path | None = None) -> dict:
    """The seeded synthetic tenant (data.generator, seed 20260912), same backtest, same two metrics,
    so the real-data figures are comparable. `committed_2026-09-20` is the older committed MAPE."""
    with tempfile.TemporaryDirectory() as tmp:
        src = data_dir or Path(tmp) / "tenant"
        if data_dir is None:
            generate(src, 20260912)
        store = LocalStore(Path(tmp) / "work")
        for t in ("nodes", "products", "sales_daily"):
            store.write(t, LocalStore(src).read(t))
        rows = run_backtest(store, "synthetic_reference", "0")
        m = slot_metrics(store)
    assert abs(m["mean_ape_rewalk"] - _means(rows)["mean_mape"]) < 1e-3, "re-walk disagrees with run_backtest"
    old = [json.loads(x) for x in open(ROOT / "eval/raw/backtest_rows_2026-09-20.jsonl", encoding="utf-8") if x.strip()]
    return {"source": "data.generator seed 20260912, current tree", "n_rows": len(rows), **_means(rows), **{k: m[k] for k in ("wape", "scored_series_days", "median_ape", "share_ape_over_100pct")},
            "committed_2026-09-20": {"source": "eval/raw/backtest_rows_2026-09-20.jsonl", "n_rows": len(old), **_means(old)}}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sample", type=Path, default=ROOT / "data/external/online_retail_ii/sample")
    ap.add_argument("--date", default=date.today().isoformat())
    a = ap.parse_args(argv)
    out = run(a.sample, a.date)
    out["synthetic_reference"] = synthetic_reference()
    path = ROOT / "eval/raw" / f"external_backtest_{a.date}.json"
    path.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: out[k] for k in ("mean_mape", "wape", "mean_bias", "series_weighted_mape", "n_origins", "forecast_method_counts", "gap_detector")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
