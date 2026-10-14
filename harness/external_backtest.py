"""Run Taal's own backtest (jobs.sense.backtest.run_backtest, unchanged) and gap detector on the
committed Online Retail II sample (data/external/online_retail_ii) and write summary numbers only.

    uv run python -m harness.external_backtest [--sample DIR] [--date YYYY-MM-DD]
    -> eval/raw/external_backtest_<date>.json

The gap detector needs on-hand stock (and, for four of its types, an expiry date); the dataset has
neither, so it runs on an empty inventory and reports what it finds (0), plus which inputs are missing.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
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


BASELINE_WINDOW = 28  # trailing days for the mean baseline, and the history a series needs to be scored


def seasonal_naive(series: dict[date, float], d: date, origin: date) -> float:
    """Units sold on the same weekday one week earlier (a day with no row is a day with no sale: 0).
    Walks back whole weeks until the day is strictly before `origin`, so it never reads a day the
    forecaster could not have seen (for the 7-day horizon that is always d - 7)."""
    k = max(1, math.ceil(((d - origin).days + 1) / 7))
    return series.get(d - timedelta(days=7 * k), 0.0)


def trailing_mean(series: dict[date, float], origin: date, window: int = BASELINE_WINDOW) -> float:
    """Mean units per calendar day over the `window` days before `origin` (no-sale days count as 0)."""
    return sum(series.get(origin - timedelta(days=j), 0.0) for j in range(1, window + 1)) / window


def trailing_mean_sale_days(series: dict[date, float], origin: date, window: int = BASELINE_WINDOW) -> float:
    """Sensitivity variant, not one of the two headline baselines: mean over only the days with a sale
    in the window (the convention SeriesModel's own level uses). 0 when there was no sale in the window."""
    vals = [series[d] for j in range(1, window + 1) if (d := origin - timedelta(days=j)) in series]
    return sum(vals) / len(vals) if vals else 0.0


def score(pairs: list[tuple[float, float]]) -> dict:
    """(actual, forecast) pairs, all with actual > 0 -> pooled WAPE and pooled mean APE."""
    sa = sum(a for a, _ in pairs)
    return {"wape": round(sum(abs(p - a) for a, p in pairs) / sa, 4),
            "mean_ape_pooled": round(sum(abs(p - a) / a for a, p in pairs) / len(pairs), 4)}


def baseline_comparison(store: LocalStore) -> dict:
    """Taal, seasonal-naive and trailing-28-day mean on the SAME (series, origin, horizon-day) slots.

    Slots and filter are run_backtest's: rolling origins every 7 days, 7-day horizon, scored where
    actual > 0. A (series, origin) is dropped for ALL methods if the series' first sale is less than
    28 days before the origin (a 28-day trailing window and a last-week lookback would not exist yet).
    Each baseline reads only days < origin."""
    nodes = store.read("nodes")
    cluster_of = {n["node_id"]: n["cluster_id"] for n in nodes}
    tier_of = {p["sku"]: p["category"] for p in store.read("products")}
    hist, _ = _load_history(store, cluster_of)
    origins = _origins({d for series in hist.values() for d in series}, HORIZON)
    methods = ("taal", "seasonal_naive", "trailing_28d_mean", "trailing_28d_mean_sale_days_only")
    pairs: dict[str, list[tuple[float, float]]] = {m: [] for m in methods}
    cells: dict[str, dict[tuple[date, str], list[float]]] = {m: defaultdict(list) for m in methods}
    excluded: list[tuple[str, date]] = []
    for origin in origins:
        for (sku, _cluster), series in sorted(hist.items()):
            if sku not in tier_of:
                continue
            if min(series) > origin - timedelta(days=BASELINE_WINDOW):
                excluded.append((sku, origin))
                continue
            units = {d: v[0] for d, v in series.items() if d < origin}
            model = SeriesModel({d: v for d, v in series.items() if d < origin}, origin)
            mean28, mean_sd = trailing_mean(units, origin), trailing_mean_sale_days(units, origin)
            for i in range(HORIZON):
                d = origin + timedelta(days=i)
                a, promo = series.get(d, (0.0, False))
                if a <= 0:
                    continue
                preds = {"taal": model.p50(d, on_promo=promo, is_festival=False),
                         "seasonal_naive": seasonal_naive(units, d, origin),
                         "trailing_28d_mean": mean28, "trailing_28d_mean_sale_days_only": mean_sd}
                for m, p in preds.items():
                    pairs[m].append((a, p))
                    cells[m][(origin, tier_of[sku])].append(abs(p - a) / a)
    out = {}
    for m in methods:
        sc = score(pairs[m])
        sc["mean_mape"] = round(sum(sum(v) / len(v) for v in cells[m].values()) / len(cells[m]), 4)
        sc["pooled_bias"] = round(sum(p - a for a, p in pairs[m]) / sum(a for a, _ in pairs[m]), 4)  # sum(f - a) / sum(a), not the main report's per-day relative bias
        out[m] = {"scored_series_days": len(pairs[m]), **sc}
    return {"methods": out, "origins": [o.isoformat() for o in origins],
            "excluded_series_origins": len(excluded), "excluded_series": len({s for s, _ in excluded}),
            "excluded_detail": [[s, o.isoformat()] for s, o in excluded],
            "series_origin_pairs_total": len(origins) * len(tier_of)}


# ---------------------------------------------------------------------------------------------
# Fair metrics and candidates (protocol: eval/backtest_protocol_2026-10-14.md, committed before this
# code was run). Backtest-only variants, labelled "candidate, not shipped"; jobs/sense/forecast.py is
# imported and never modified. Every method function takes the history and the origin and itself drops
# every day at or after the origin before using anything.
# ---------------------------------------------------------------------------------------------
PROTOCOL = ROOT / "eval/backtest_protocol_2026-10-14.md"
TUNE_ORIGINS = 4  # first four of the eight origins (ascending) tune; the last four report
FAST_MIN_SALE_DAYS = 15
ALPHA_GRID = (0.05, 0.1, 0.2, 0.3)
WEEKDAY_WINDOW = 91
EW_WINDOW, EW_HALF_LIFE = 56, 14
CANDIDATES = ("v1", "v2", "v3", "v4", "v5")
BASELINES = ("seasonal_naive", "mean28", "median28", "croston", "sba")
METHODS = ("taal", *BASELINES, *CANDIDATES)
CANDIDATE_LABEL = "candidate, not shipped"

History = dict[date, tuple[float, bool]]


def _units(hist: History, origin: date) -> dict[date, float]:
    """Units per day for days strictly before `origin`; the only way any method below reads history."""
    return {d: v[0] for d, v in hist.items() if d < origin}


def _zero_filled(units: dict[date, float], origin: date, n: int) -> list[float]:
    """Units for the n days before the origin, oldest first, no-sale days as 0."""
    return [units.get(origin - timedelta(days=j), 0.0) for j in range(n, 0, -1)]


def horizon_days(origin: date) -> list[date]:
    return [origin + timedelta(days=i) for i in range(HORIZON)]


def f_taal(hist: History, origin: date) -> list[float]:
    m = SeriesModel({d: v for d, v in hist.items() if d < origin}, origin)
    return [m.p50(d, on_promo=False, is_festival=False) for d in horizon_days(origin)]


def f_seasonal_naive(hist: History, origin: date) -> list[float]:
    u = _units(hist, origin)
    return [seasonal_naive(u, d, origin) for d in horizon_days(origin)]


def f_mean28(hist: History, origin: date) -> list[float]:
    return [sum(_zero_filled(_units(hist, origin), origin, BASELINE_WINDOW)) / BASELINE_WINDOW] * HORIZON


def f_median28(hist: History, origin: date) -> list[float]:
    return [statistics.median(_zero_filled(_units(hist, origin), origin, BASELINE_WINDOW))] * HORIZON


def croston_state(units: dict[date, float], origin: date, alpha: float) -> tuple[float, float]:
    """Croston's (z, p): smoothed demand size and smoothed interval between demands, over every demand
    day (units > 0) before the origin, from the series' first demand. z0 = first demand, p0 = 1.
    No demand before the origin -> (0, 1)."""
    days = sorted(d for d, u in units.items() if d < origin and u > 0)
    if not days:
        return 0.0, 1.0
    z, p, prev = units[days[0]], 1.0, days[0]
    for d in days[1:]:
        z += alpha * (units[d] - z)
        p += alpha * ((d - prev).days - p)
        prev = d
    return z, p


def f_croston(hist: History, origin: date, alpha: float = 0.1) -> list[float]:
    z, p = croston_state(_units(hist, origin), origin, alpha)
    return [z / p] * HORIZON


def f_sba(hist: History, origin: date, alpha: float = 0.1) -> list[float]:
    """Syntetos-Boylan approximation: Croston's z / p scaled by (1 - alpha / 2) to remove its upward bias."""
    z, p = croston_state(_units(hist, origin), origin, alpha)
    return [(1 - alpha / 2) * z / p] * HORIZON


def _taal_dow(hist: History, origin: date) -> list[float]:
    return SeriesModel({d: v for d, v in hist.items() if d < origin}, origin).dow


def _shaped(level: float, dow: list[float], origin: date) -> list[float]:
    return [level * dow[d.weekday()] for d in horizon_days(origin)]


def f_v1(hist: History, origin: date) -> list[float]:
    """Taal's weekday shape on a zero-filled level (units per calendar day, not per sale day)."""
    level = sum(_zero_filled(_units(hist, origin), origin, BASELINE_WINDOW)) / BASELINE_WINDOW
    return _shaped(level, _taal_dow(hist, origin), origin)


def f_v2(hist: History, origin: date) -> list[float]:
    """V1 blended 50/50 with the trailing 28-day zero-filled mean."""
    return [0.5 * a + 0.5 * b for a, b in zip(f_v1(hist, origin), f_mean28(hist, origin), strict=True)]


def f_v3(hist: History, origin: date) -> list[float]:
    """V1 with Taal's weekday multipliers shrunk a further 50% toward 1."""
    level = sum(_zero_filled(_units(hist, origin), origin, BASELINE_WINDOW)) / BASELINE_WINDOW
    return _shaped(level, [0.5 * k + 0.5 for k in _taal_dow(hist, origin)], origin)


def zero_filled_dow(units: dict[date, float], origin: date, window: int = WEEKDAY_WINDOW) -> list[float]:
    """Weekday multipliers from the `window` days before the origin, no-sale days counted: mean units on
    weekday k over the mean of all window days (1.0 for every weekday if the window has no sales)."""
    vals = {origin - timedelta(days=j): units.get(origin - timedelta(days=j), 0.0) for j in range(1, window + 1)}
    mean_all = sum(vals.values()) / window
    out = []
    for k in range(7):
        ks = [v for d, v in vals.items() if d.weekday() == k]
        out.append((sum(ks) / len(ks)) / mean_all if ks and mean_all > 0 else 1.0)
    return out


def f_v4(hist: History, origin: date) -> list[float]:
    """Zero-filled weekday multipliers (last 91 days), shrunk 50% toward 1, on the zero-filled level."""
    u = _units(hist, origin)
    level = sum(_zero_filled(u, origin, BASELINE_WINDOW)) / BASELINE_WINDOW
    return _shaped(level, [0.5 * k + 0.5 for k in zero_filled_dow(u, origin)], origin)


def ew_level(units: dict[date, float], origin: date, window: int = EW_WINDOW, half_life: float = EW_HALF_LIFE) -> float:
    """Exponentially weighted zero-filled mean; the day before the origin has age 0, weight 0.5^(age/half_life)."""
    w = [0.5 ** ((j - 1) / half_life) for j in range(1, window + 1)]
    return sum(wj * units.get(origin - timedelta(days=j), 0.0) for j, wj in zip(range(1, window + 1), w, strict=True)) / sum(w)


def f_v5(hist: History, origin: date) -> list[float]:
    """V1 with the level replaced by the exponentially weighted zero-filled mean (follows a ramp)."""
    return _shaped(ew_level(_units(hist, origin), origin), _taal_dow(hist, origin), origin)


def method_functions() -> dict:
    """name -> f(history, origin) -> 7 forecasts. Croston and SBA appear once per alpha in the grid."""
    fns = {"taal": f_taal, "seasonal_naive": f_seasonal_naive, "mean28": f_mean28, "median28": f_median28,
           "v1": f_v1, "v2": f_v2, "v3": f_v3, "v4": f_v4, "v5": f_v5}
    for a in ALPHA_GRID:
        fns[f"croston@{a}"] = lambda h, o, a=a: f_croston(h, o, a)
        fns[f"sba@{a}"] = lambda h, o, a=a: f_sba(h, o, a)
    return fns


def mase_scale(units: dict[date, float], origin: date, window: int = BASELINE_WINDOW) -> float:
    """In-sample seasonal-naive-7 mean absolute error over the `window` days before the origin:
    mean over d in [O - window, O - 1] of |y(d) - y(d - 7)|. Reads only days < origin."""
    ds = [origin - timedelta(days=j) for j in range(1, window + 1)]
    return sum(abs(units.get(d, 0.0) - units.get(d - timedelta(days=7), 0.0)) for d in ds) / window


def mase_pair(forecast: list[float], actual: list[float], scale: float) -> float:
    return (sum(abs(f - a) for f, a in zip(forecast, actual, strict=True)) / len(actual)) / scale


def build_pairs(hist: dict, tier_of: dict, origins: list[date], fns: dict) -> tuple[list[dict], list[tuple[str, date]]]:
    """One record per (series, origin): the 7 actuals, the fast-mover flag, the MASE scale and every
    method's 7 forecasts. A pair is dropped (for all methods) when the series' first sale is less than 28
    days before the origin, as in the Baselines section. Methods are called with the full series but each
    drops days >= origin itself."""
    pairs: list[dict] = []
    excluded: list[tuple[str, date]] = []
    for origin in origins:
        for (sku, _cluster), series in sorted(hist.items()):
            if sku not in tier_of:
                continue
            if min(series) > origin - timedelta(days=BASELINE_WINDOW):
                excluded.append((sku, origin))
                continue
            u = _units(series, origin)
            pairs.append({
                "sku": sku, "origin": origin,
                "actual": [series.get(d, (0.0, False))[0] for d in horizon_days(origin)],
                "fast": sum(1 for v in _zero_filled(u, origin, BASELINE_WINDOW) if v > 0) >= FAST_MIN_SALE_DAYS,
                "scale": mase_scale(u, origin),
                "taal_intermittent": SeriesModel({d: v for d, v in series.items() if d < origin}, origin).is_intermittent,
                "preds": {name: fn(series, origin) for name, fn in fns.items()},
            })
    return pairs, excluded


def group_metrics(pairs: list[dict], method: str, origins: set[date] | None = None, fast_only: bool = False) -> dict:
    """The protocol's metrics for one method over the pairs in `origins` (all if None), optionally the
    fast-mover slice. Pooled WAPE/bias; MASE is the mean (and median) of per-pair MASE."""
    ps = [p for p in pairs if (origins is None or p["origin"] in origins) and (p["fast"] or not fast_only)]
    inc = [p for p in ps if sum(p["actual"]) > 0]            # window with any sale: all-days WAPE, weekly, bias
    sa = sum(sum(p["actual"]) for p in inc)
    err = sum(abs(f - a) for p in inc for f, a in zip(p["preds"][method], p["actual"], strict=True))
    fsum = sum(sum(p["preds"][method]) for p in inc)
    slots = [(a, f, p["origin"]) for p in ps for a, f in zip(p["actual"], p["preds"][method], strict=True) if a > 0]
    sd_act = sum(a for a, _, _ in slots)
    ape: dict[date, list[float]] = defaultdict(list)
    for a, f, o in slots:
        ape[o].append(abs(f - a) / a)
    msc = [mase_pair(p["preds"][method], p["actual"], p["scale"]) for p in ps if p["scale"] > 0]
    sa_all = sum(sum(p["actual"]) for p in ps)
    err_all = sum(abs(f - a) for p in ps for f, a in zip(p["preds"][method], p["actual"], strict=True))
    weekly_err = sum(abs(sum(p["preds"][method]) - sum(p["actual"])) for p in inc)
    r = lambda x: round(x, 4) if x is not None else None  # noqa: E731
    return {
        "n_pairs": len(ps), "n_pairs_scored_all_days": len(inc), "n_sale_day_slots": len(slots),
        "all_days_wape": r(err / sa) if sa else None,
        "all_days_wape_no_exclusion": r(err_all / sa_all) if sa_all else None,
        "sale_day_wape": r(sum(abs(f - a) for a, f, _ in slots) / sd_act) if sd_act else None,
        "mase_mean": r(statistics.mean(msc)) if msc else None, "mase_median": r(statistics.median(msc)) if msc else None,
        "weekly_wape": r(weekly_err / sa) if sa else None,
        "bias_all_days": r((fsum - sa) / sa) if sa else None,
        "bias_sale_days": r(sum(f - a for a, f, _ in slots) / sd_act) if sd_act else None,
        "mape_continuity_only": r(statistics.mean(statistics.mean(v) for v in ape.values())) if ape else None,
    }


def group_exclusions(pairs: list[dict], origins: set[date] | None, fast_only: bool) -> dict:
    ps = [p for p in pairs if (origins is None or p["origin"] in origins) and (p["fast"] or not fast_only)]
    return {"pairs": len(ps), "excluded_zero_actual_window": sum(1 for p in ps if sum(p["actual"]) == 0),
            "excluded_mase_scale_zero": sum(1 for p in ps if p["scale"] == 0)}


LOWER_BETTER = ("all_days_wape", "sale_day_wape", "mase_mean", "mase_median", "weekly_wape", "bias_all_days_abs", "mape_continuity_only")


def _cmp_value(m: dict, key: str):
    return abs(m["bias_all_days"]) if key == "bias_all_days_abs" else m[key]


def weekday_diagnostics(pairs: list[dict], methods: dict[str, str], origins: set[date]) -> dict:
    """POST-HOC reading aid, written after the first run and not an input to any rule: per weekday (Mon=0),
    total actual and total forecast units over the REPORT pairs with any sale, and the all-days WAPE with
    the weekday that had no sale at all in the group removed (the retailer takes no Saturday orders)."""
    inc = [p for p in pairs if p["origin"] in origins and sum(p["actual"]) > 0]
    days = {p["origin"]: horizon_days(p["origin"]) for p in inc}
    actual = {k: round(sum(p["actual"][i] for p in inc for i, d in enumerate(days[p["origin"]]) if d.weekday() == k), 1) for k in range(7)}
    closed = [k for k, v in actual.items() if v == 0]
    out: dict = {"group": "REPORT", "actual_units_by_weekday": actual, "weekdays_with_zero_actual": closed, "methods": {}}
    for label, name in methods.items():
        fc = {k: round(sum(p["preds"][name][i] for p in inc for i, d in enumerate(days[p["origin"]]) if d.weekday() == k), 1) for k in range(7)}
        keep = [(a, f) for p in inc for d, a, f in zip(days[p["origin"]], p["actual"], p["preds"][name], strict=True) if d.weekday() not in closed]
        out["methods"][label] = {"forecast_units_by_weekday": fc,
                                 "forecast_units_on_zero_actual_weekdays": round(sum(fc[k] for k in closed), 1),
                                 "all_days_wape_excluding_zero_actual_weekdays": round(sum(abs(f - a) for a, f in keep) / sum(a for a, _ in keep), 4)}
    return out


def fallback_slice(pairs: list[dict], methods: dict[str, str], origins: set[date]) -> dict:
    """POST-HOC reading aid (not a rule input): REPORT windows split by whether the shipped SeriesModel
    puts the series in its `average_demand_intermittent` fallback (fewer than 14 sale days in the last 28)."""
    out: dict = {"group": "REPORT"}
    for label, flag in (("taal_intermittent_fallback", True), ("taal_seasonal_model", False)):
        ps = [p for p in pairs if p["origin"] in origins and p["taal_intermittent"] is flag]
        out[label] = {"n_pairs": len(ps), "methods": {
            m: {k: group_metrics(ps, methods[m])[k] for k in ("all_days_wape", "bias_all_days", "sale_day_wape", "bias_sale_days")}
            for m in ("taal", "mean28", "v1", "v4")}}
    return out


def fair_metrics(hist: dict, tier_of: dict, origins: list[date]) -> dict:
    fns = method_functions()
    pairs, excluded = build_pairs(hist, tier_of, origins, fns)
    asc = sorted(origins)
    groups = {"TUNE": set(asc[:TUNE_ORIGINS]), "REPORT": set(asc[TUNE_ORIGINS:]), "ALL": set(asc)}
    # alpha for Croston and SBA: lowest TUNE all-days WAPE over the grid (ties: smaller alpha)
    grid = {fam: {a: {g: group_metrics(pairs, f"{fam}@{a}", groups[g])["all_days_wape"] for g in groups} for a in ALPHA_GRID} for fam in ("croston", "sba")}
    alpha = {fam: min(ALPHA_GRID, key=lambda a, fam=fam: (grid[fam][a]["TUNE"], a)) for fam in grid}
    resolve = {m: (f"{m}@{alpha[m]}" if m in alpha else m) for m in METHODS}
    results: dict = {}
    for g, os_ in groups.items():
        results[g] = {}
        for sl, fast in (("all", False), ("fast_movers", True)):
            results[g][sl] = {"exclusions": group_exclusions(pairs, os_, fast),
                              "methods": {m: group_metrics(pairs, resolve[m], os_, fast) for m in METHODS}}
    # primary candidate: lowest TUNE all-days WAPE among V1..V5 (ties: lower number)
    tune = results["TUNE"]["all"]["methods"]
    primary = min(CANDIDATES, key=lambda m: (tune[m]["all_days_wape"], m))
    rep = results["REPORT"]["all"]["methods"]
    rule = {"primary_candidate": primary, "label": CANDIDATE_LABEL,
            "selected_on": "lowest all-days WAPE on TUNE origins",
            "tune_all_days_wape": {m: tune[m]["all_days_wape"] for m in CANDIDATES},
            "report_all_days_wape": {m: rep[m]["all_days_wape"] for m in ("taal", *BASELINES, *CANDIDATES)},
            "beats_unchanged_taal": rep[primary]["all_days_wape"] < rep["taal"]["all_days_wape"],
            "beats_every_baseline": all(rep[primary]["all_days_wape"] < rep[b]["all_days_wape"] for b in BASELINES)}
    best_base = min(BASELINES, key=lambda b: rep[b]["all_days_wape"])
    rule["best_baseline_on_report"] = best_base
    rule["margin_vs_taal"] = round(rep["taal"]["all_days_wape"] - rep[primary]["all_days_wape"], 4)
    rule["margin_vs_best_baseline"] = round(rep[best_base]["all_days_wape"] - rep[primary]["all_days_wape"], 4)
    rule["meets_pre_registered_rule"] = rule["beats_unchanged_taal"] and rule["beats_every_baseline"]
    rule["others_descriptive"] = {m: {"beats_taal": rep[m]["all_days_wape"] < rep["taal"]["all_days_wape"],
                                      "beats_every_baseline": all(rep[m]["all_days_wape"] < rep[b]["all_days_wape"] for b in BASELINES)} for m in CANDIDATES}
    taal_vs = {g: {sl: {b: {k: _cmp_value(results[g][sl]["methods"]["taal"], k) < _cmp_value(results[g][sl]["methods"][b], k) for k in LOWER_BETTER}
                         for b in BASELINES} for sl in ("all", "fast_movers")} for g in groups}
    per_origin = {m: {o.isoformat(): group_metrics(pairs, resolve[m], {o})["all_days_wape"] for o in asc} for m in METHODS}
    rep_pairs = [p for p in pairs if p["origin"] in groups["REPORT"]]
    return {
        "origins": {g: sorted(o.isoformat() for o in os_) for g, os_ in groups.items()},
        "chosen_alpha": alpha, "alpha_grid_all_days_wape": {fam: {str(a): v for a, v in d.items()} for fam, d in grid.items()},
        "results": results, "decision_rule": rule,
        "taal_beats_baseline_lower_is_better": taal_vs,
        "per_origin_all_days_wape": per_origin,
        "post_hoc_diagnostics": {**weekday_diagnostics(pairs, resolve, groups["REPORT"]), "by_taal_fallback": fallback_slice(pairs, resolve, groups["REPORT"])},
        "diagnostics": {"share_report_pairs_taal_intermittent_fallback": round(sum(1 for p in rep_pairs if p["taal_intermittent"]) / len(rep_pairs), 4),
                        "excluded_first_sale_within_28d": {"series_origin_pairs": len(excluded)},
                        "n_pairs_total": len(pairs)},
    }


def run_fair(sample: Path) -> dict:
    tables = sample_to_tables(sample)
    with tempfile.TemporaryDirectory() as tmp:
        store = LocalStore(tmp)
        for t, rows in tables.items():
            store.write(t, rows)
        cluster_of = {n["node_id"]: n["cluster_id"] for n in store.read("nodes")}
        tier_of = {p["sku"]: p["category"] for p in store.read("products")}
        hist, _ = _load_history(store, cluster_of)
        origins = _origins({d for series in hist.values() for d in series}, HORIZON)
        fm = fair_metrics(hist, tier_of, origins)
    return {
        "task": "external backtest v2: fair metrics (zeros counted, MASE, weekly), more baselines, backtest-only candidates",
        "protocol": {"file": str(PROTOCOL.relative_to(ROOT)), "sha256": _sha256(PROTOCOL),
                     "pre_registered": "committed before the first run of this code; see git history"},
        "inputs": {"dataset": "UCI Online Retail II (CC BY 4.0), top 300 SKUs by units, node = country, one cluster",
                   "sample_sha256": {f.name: _sha256(f) for f in sorted(sample.iterdir()) if f.is_file()},
                   "series": len({p["sku"] for p in tables["products"]})},
        "shipped_forecaster_changed": False, "candidates": {m: CANDIDATE_LABEL for m in CANDIDATES},
        "method_definitions": {"taal": "SeriesModel, unchanged", "seasonal_naive": "same weekday last week", "mean28": "28-day zero-filled mean, flat",
                               "median28": "28-day zero-filled median, flat", "croston": "Croston, alpha chosen on TUNE", "sba": "Syntetos-Boylan, alpha chosen on TUNE",
                               "v1": "mean28 x Taal weekday multipliers", "v2": "50/50 V1 and mean28", "v3": "V1 with multipliers shrunk 50% toward 1",
                               "v4": "mean28 x (zero-filled 91-day weekday multipliers shrunk 50%)", "v5": "V1 with exponentially weighted (half-life 14d, 56d) level"},
        "random_seed": "none; deterministic",
        **fm,
    }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_baselines(sample: Path) -> dict:
    tables = sample_to_tables(sample)
    with tempfile.TemporaryDirectory() as tmp:
        store = LocalStore(tmp)
        for t, rows in tables.items():
            store.write(t, rows)
        cmp = baseline_comparison(store)
    taal = cmp["methods"]["taal"]
    return {
        "task": "external backtest baselines: Taal vs seasonal-naive vs trailing 28-day mean, same slots, same scoring",
        "inputs": {
            "dataset": "UCI Online Retail II (CC BY 4.0), top 300 SKUs by units, node = country, one cluster",
            "sample_dir": "data/external/online_retail_ii/sample",
            "sample_sha256": {f.name: _sha256(f) for f in sorted(sample.iterdir()) if f.is_file()},
            "series": len({p["sku"] for p in tables["products"]}),
            "history": {"first": min(s["date"] for s in tables["sales_daily"]), "last": max(s["date"] for s in tables["sales_daily"])},
        },
        "protocol": {
            "origins": cmp["origins"], "horizon_days": HORIZON, "origin_step_days": 7,
            "train_test_boundary": "for each origin O: fit/lookup uses only days strictly before O; the test days are O .. O+6",
            "scored_slot": "(series, origin, horizon day) with actual units > 0; no-sale days are not scored, as in run_backtest",
            "metrics": {"wape": "sum|forecast - actual| / sum(actual) over all scored series-days, pooled",
                        "mean_mape": "run_backtest convention: mean of per-origin mean absolute percentage error (one tier)"},
            "exclusion_rule": f"a (series, origin) is dropped for all methods when the series' first sale is less than {BASELINE_WINDOW} days before the origin",
            "random_seed": "none; the run is deterministic",
        },
        "methods": {
            "taal": "jobs.sense.forecast.SeriesModel.p50, refit on days < origin (as run_backtest), no promo/festival flag",
            "seasonal_naive": "units on the same weekday one week before the forecast day (d - 7, always < origin for a 7-day horizon); no row = 0",
            "trailing_28d_mean": f"mean units per calendar day over the {BASELINE_WINDOW} days before the origin, no-sale days counted as 0; one flat value for all 7 horizon days",
            "trailing_28d_mean_sale_days_only": "sensitivity only, not a headline baseline: same window, mean over days that had a sale (SeriesModel's own level convention)",
        },
        "results": cmp["methods"],
        "exclusions": {k: cmp[k] for k in ("excluded_series_origins", "excluded_series", "series_origin_pairs_total", "excluded_detail")},
        "taal_vs_baselines": {
            b: {"wape_relative_reduction": round(1 - taal["wape"] / cmp["methods"][b]["wape"], 4),
                "mape_relative_reduction": round(1 - taal["mean_mape"] / cmp["methods"][b]["mean_mape"], 4),
                "taal_beats_on_wape": taal["wape"] < cmp["methods"][b]["wape"],
                "taal_beats_on_mape": taal["mean_mape"] < cmp["methods"][b]["mean_mape"]}
            for b in ("seasonal_naive", "trailing_28d_mean", "trailing_28d_mean_sale_days_only")},
    }


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
    ap.add_argument("--baselines", action="store_true", help="write eval/raw/external_backtest_baselines_<date>.json only")
    ap.add_argument("--fair", action="store_true", help="write eval/raw/external_backtest_v2_<date>.json (fair metrics and candidates)")
    a = ap.parse_args(argv)
    if a.fair:
        res = run_fair(a.sample)
        path = ROOT / "eval/raw" / f"external_backtest_v2_{a.date}.json"
        path.write_text(json.dumps(res, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"chosen_alpha": res["chosen_alpha"], "decision_rule": res["decision_rule"]}, indent=2))
        return 0
    if a.baselines:
        res = run_baselines(a.sample)
        path = ROOT / "eval/raw" / f"external_backtest_baselines_{a.date}.json"
        path.write_text(json.dumps(res, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"results": res["results"], "exclusions": {k: v for k, v in res["exclusions"].items() if k != "excluded_detail"}}, indent=2))
        return 0
    out = run(a.sample, a.date)
    out["synthetic_reference"] = synthetic_reference()
    path = ROOT / "eval/raw" / f"external_backtest_{a.date}.json"
    path.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: out[k] for k in ("mean_mape", "wape", "mean_bias", "series_weighted_mape", "n_origins", "forecast_method_counts", "gap_detector")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
