"""Local forecaster standing in for BigQuery `AI.FORECAST` (TimesFM) and `ML.FORECAST` on an
`ARIMA_PLUS_XREG` model with `future_regressors` (DECISIONS §5.2). Same table shapes, same run
semantics; the model column says `local_seasonal_xreg` so no chart can pass it off as TimesFM.

Method (per sku x cluster, then rolled down to nodes by trailing 28-day share):
  level          = mean daily units over the last 28 days of history
  dow[k]         = mean units on weekday k / overall mean over the full history (smoothed toward 1)
  promo_coef     = mean units on promo days / mean on non-promo days, clamped to [1.1, 2.5]
  festival_coef  = 1.35 (fixed, labelled; ARIMA_PLUS_XREG estimates it in production)
  p50(d)         = level * dow[d] * promo_coef^on_promo(d) * festival_coef^is_festival(d)
  p10 / p90      = p50 * empirical 10th / 90th percentile of actual/fitted over the last 28 days
A play approved for a sku sets on_promo=true on its window dates in future_regressors; the
re-forecast changes p50 inside the window and nowhere before it (tests/sql/test_forecast.py).
"""
from __future__ import annotations

import hashlib
from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from agents.gate.store import LocalStore

HORIZON = 28
LEVEL_WINDOW = 28
FESTIVAL_COEF = 1.35
MODEL = "local_seasonal_xreg"


def run_id_for(as_of: date, tag: str = "baseline") -> str:
    h = hashlib.sha256(f"{as_of.isoformat()}|{tag}".encode()).hexdigest()[:8]
    return f"sense_{as_of.strftime('%Y%m%d')}_{tag}_{h}"


def _percentile(values: list[float], q: float) -> float:
    if not values:
        return 1.0
    s = sorted(values)
    k = (len(s) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


class SeriesModel:
    """One sku x cluster series fitted from daily history."""

    def __init__(self, history: dict[date, tuple[float, bool]], as_of: date):
        self.as_of = as_of
        days = sorted(history)
        if not days:
            self.level, self.dow, self.promo_coef, self.q10, self.q90 = 0.0, [1.0] * 7, 1.3, 0.6, 1.5
            return
        start = as_of - timedelta(days=LEVEL_WINDOW)
        overall = [u for d, (u, _) in history.items()]
        mean_all = sum(overall) / len(overall) if overall else 0.0
        by_dow: dict[int, list[float]] = defaultdict(list)
        for d, (u, _) in history.items():
            by_dow[d.weekday()].append(u)
        self.dow = []
        for k in range(7):
            vals = by_dow.get(k, [])
            raw = (sum(vals) / len(vals)) / mean_all if vals and mean_all > 0 else 1.0
            self.dow.append(0.7 * raw + 0.3)  # shrink toward 1
        promo = [u for d, (u, p) in history.items() if p]
        non = [u for d, (u, p) in history.items() if not p]
        coef = (sum(promo) / len(promo)) / (sum(non) / len(non)) if promo and non and sum(non) > 0 else 1.3
        self.promo_coef = min(2.5, max(1.1, coef))
        recent = [(d, u, p) for d, (u, p) in history.items() if d >= start]
        base = [u / (self.promo_coef if p else 1.0) for _, u, p in recent]
        self.level = sum(base) / len(base) if base else mean_all
        ratios = []
        for d, u, p in recent:
            fitted = self.level * self.dow[d.weekday()] * (self.promo_coef if p else 1.0)
            if fitted > 0:
                ratios.append(u / fitted)
        self.q10 = max(0.0, min(1.0, _percentile(ratios, 0.10))) if ratios else 0.6
        self.q90 = max(1.0, _percentile(ratios, 0.90)) if ratios else 1.5

    def p50(self, d: date, on_promo: bool, is_festival: bool) -> float:
        v = self.level * self.dow[d.weekday()]
        if on_promo:
            v *= self.promo_coef
        if is_festival:
            v *= FESTIVAL_COEF
        return v


def _load_history(store: LocalStore, cluster_of: dict[str, str]) -> tuple[dict[tuple[str, str], dict[date, tuple[float, bool]]], dict[tuple[str, str], float]]:
    """Cluster-level history and trailing-28-day node shares."""
    cluster_hist: dict[tuple[str, str], dict[date, list]] = defaultdict(lambda: defaultdict(lambda: [0.0, False]))
    node_recent: dict[tuple[str, str], float] = defaultdict(float)
    max_date: date | None = None
    rows = store.read("sales_daily")
    for r in rows:
        d = date.fromisoformat(r["date"])
        if max_date is None or d > max_date:
            max_date = d
    cutoff = (max_date or date.min) - timedelta(days=LEVEL_WINDOW - 1)
    for r in rows:
        d = date.fromisoformat(r["date"])
        key = (r["sku"], cluster_of[r["node_id"]])
        cell = cluster_hist[key][d]
        cell[0] += r["units"]
        cell[1] = cell[1] or bool(r["on_promo"])
        if d >= cutoff:
            node_recent[(r["sku"], r["node_id"])] += r["units"]
    hist = {k: {d: (v[0], v[1]) for d, v in days.items()} for k, days in cluster_hist.items()}
    return hist, node_recent


def forecast(store: LocalStore, as_of: date, run_id: str, skus: list[str] | None = None, includes_plays: bool = False) -> list[dict[str, Any]]:
    """Node-level forecast rows for HORIZON days from as_of, reading future_regressors for the
    on_promo / is_festival flags. Rows carry cluster_id so the cluster series can be re-summed."""
    nodes = store.read("nodes")
    cluster_of = {n["node_id"]: n["cluster_id"] for n in nodes}
    nodes_in_cluster: dict[str, list[str]] = defaultdict(list)
    for n in nodes:
        nodes_in_cluster[n["cluster_id"]].append(n["node_id"])
    hist, node_recent = _load_history(store, cluster_of)
    regs: dict[tuple[str, str, str], tuple[bool, bool]] = {}
    for r in store.read("future_regressors"):
        key = (r["date"], r["sku"], r["cluster_id"])
        prev = regs.get(key, (False, False))
        regs[key] = (prev[0] or bool(r["on_promo"]), prev[1] or bool(r["is_festival"]))
    want = set(skus) if skus else None
    out: list[dict[str, Any]] = []
    tenant = nodes[0]["tenant_id"] if nodes else "unknown"
    for (sku, cluster), series in sorted(hist.items()):
        if want is not None and sku not in want:
            continue
        model = SeriesModel(series, as_of)
        members = nodes_in_cluster[cluster]
        total_recent = sum(node_recent.get((sku, n), 0.0) for n in members)
        shares = {n: (node_recent.get((sku, n), 0.0) / total_recent if total_recent > 0 else 1.0 / len(members)) for n in members}
        for i in range(HORIZON):
            d = as_of + timedelta(days=i)
            on_promo, is_fest = regs.get((d.isoformat(), sku, cluster), (False, False))
            p50c = model.p50(d, on_promo, is_fest)
            for n in members:
                p50 = p50c * shares[n]
                out.append({
                    "tenant_id": tenant, "run_id": run_id, "sku": sku, "node_id": n, "cluster_id": cluster, "date": d.isoformat(),
                    "p10": round(p50 * model.q10, 3), "p50": round(p50, 3), "p90": round(p50 * model.q90, 3),
                    "model": MODEL, "method": "seasonal_naive_xreg", "includes_plays": includes_plays, "as_of": as_of.isoformat(),
                })
    return out


def series_for(rows: list[dict[str, Any]], sku: str, node_ids: list[str]) -> dict[str, float]:
    """Date -> summed p50 over the given nodes."""
    acc: dict[str, float] = defaultdict(float)
    for r in rows:
        if r["sku"] == sku and r["node_id"] in node_ids:
            acc[r["date"]] += r["p50"]
    return dict(sorted(acc.items()))
