"""Customer segments (KMEANS k=6 on RFM + category share, DECISIONS §5.2 step 5) and substitute
candidates (same category, top-5, standing in for AI.GENERATE_EMBEDDING + VECTOR_SEARCH).

Pure Python, seeded, deterministic. Segment names are derived from the centroid (top category and
frequency band) so a planner can read them; in production the names are reviewed by hand and stored
in segments.name.
"""
from __future__ import annotations

import math
import random
from collections import defaultdict
from datetime import date
from typing import Any

from agents.gate.store import LocalStore

K = 6
ITERATIONS = 25


def _features(store: LocalStore, as_of: date) -> tuple[list[str], list[list[float]], list[str], dict[str, str]]:
    products = {p["sku"]: p for p in store.read("products")}
    cats = sorted({p["category"] for p in products.values()})
    lines = store.read("order_lines")
    per: dict[str, dict[str, Any]] = defaultdict(lambda: {"last": None, "orders": set(), "spend": 0.0, "cat": defaultdict(float)})
    for ln in lines:
        c = per[ln["customer_id"]]
        d = date.fromisoformat(ln["ts"][:10])
        c["last"] = d if c["last"] is None or d > c["last"] else c["last"]
        c["orders"].add(ln["order_id"])
        amt = float(ln["qty"]) * float(ln["price"])
        c["spend"] += amt
        c["cat"][products[ln["sku"]]["category"]] += amt
    ids, X, tops = [], [], {}
    for cust in store.read("customers"):
        cid = cust["customer_id"]
        c = per.get(cid)
        if c is None or not c["orders"]:
            rec, freq, mon, shares = 120.0, 0.0, 0.0, [0.0] * len(cats)
            tops[cid] = "none"
        else:
            rec = float((as_of - c["last"]).days)
            months = max(1.0, 70 / 30)
            freq = len(c["orders"]) / months
            mon = c["spend"]
            shares = [c["cat"][k] / mon if mon > 0 else 0.0 for k in cats]
            tops[cid] = max(c["cat"], key=c["cat"].get)
        ids.append(cid)
        X.append([rec, freq, mon, *shares])
    return ids, X, cats, tops


def _standardise(X: list[list[float]]) -> tuple[list[list[float]], list[float], list[float]]:
    n, m = len(X), len(X[0])
    mean = [sum(r[j] for r in X) / n for j in range(m)]
    sd = [math.sqrt(sum((r[j] - mean[j]) ** 2 for r in X) / n) or 1.0 for j in range(m)]
    return [[(r[j] - mean[j]) / sd[j] for j in range(m)] for r in X], mean, sd


def kmeans(X: list[list[float]], k: int, seed: int) -> tuple[list[int], list[list[float]]]:
    rng = random.Random(seed)
    centroids = [list(X[i]) for i in rng.sample(range(len(X)), k)]
    labels = [0] * len(X)
    for _ in range(ITERATIONS):
        changed = False
        for i, x in enumerate(X):
            best = min(range(k), key=lambda c: sum((a - b) ** 2 for a, b in zip(x, centroids[c], strict=True)))
            if best != labels[i]:
                labels[i] = best
                changed = True
        for c in range(k):
            members = [X[i] for i in range(len(X)) if labels[i] == c]
            if members:
                centroids[c] = [sum(col) / len(members) for col in zip(*members, strict=True)]
        if not changed:
            break
    return labels, centroids


def build_segments(store: LocalStore, as_of: date, seed: int = 6) -> list[dict[str, Any]]:
    ids, X, cats, tops = _features(store, as_of)
    Z, mean, sd = _standardise(X)
    labels, centroids = kmeans(Z, K, seed)
    tenant = store.read("nodes")[0]["tenant_id"]
    segments = []
    # order segments by monetary centroid so ids are stable and readable
    order = sorted(range(K), key=lambda c: -centroids[c][2])
    remap = {c: i for i, c in enumerate(order)}
    used_names: set[str] = set()
    for c in order:
        raw = [centroids[c][j] * sd[j] + mean[j] for j in range(len(mean))]
        rec, freq, mon = raw[0], raw[1], raw[2]
        shares = raw[3:]
        top = cats[max(range(len(cats)), key=lambda j: shares[j])] if any(shares) else "mixed"
        band = "regulars" if freq >= 2.0 else ("occasionals" if freq >= 0.8 else "lapsed" if rec > 45 else "newcomers")
        name = f"{top.replace('_', ' ').title()} {band}"
        if name in used_names:
            name = f"{name} ({mon:.0f} INR)"
        used_names.add(name)
        segments.append({
            "tenant_id": tenant, "segment_id": f"seg_{remap[c] + 1}", "name": name, "k": K,
            "features": {"recency_days": round(rec, 1), "frequency_per_month": round(freq, 2), "monetary_inr": round(mon, 0), "top_category": top},
        })
    seg_of = {ids[i]: f"seg_{remap[labels[i]] + 1}" for i in range(len(ids))}
    customers = store.read("customers")
    for cust in customers:
        cust["segment_id"] = seg_of.get(cust["customer_id"], "seg_1")
    store.write("customers", customers)
    store.write("segments", segments)
    return segments


def _tokens(name: str) -> set[str]:
    return {t for t in name.lower().replace("-", " ").split() if not t[0].isdigit()}


def build_substitutes(store: LocalStore) -> list[dict[str, Any]]:
    """Top-5 same-category candidates per sku by name overlap then price proximity. Stock is filtered at chat time."""
    products = store.read("products")
    by_cat: dict[str, list[dict]] = defaultdict(list)
    for p in products:
        by_cat[p["category"]].append(p)
    out = []
    for p in products:
        t = _tokens(p["name"])
        cands = []
        for q in by_cat[p["category"]]:
            if q["sku"] == p["sku"]:
                continue
            overlap = len(t & _tokens(q["name"]))
            price_gap = abs(float(q["list_price"]) - float(p["list_price"])) / max(1.0, float(p["list_price"]))
            cands.append((-(overlap * 10) + price_gap, q["sku"]))
        cands.sort()
        out.append({"tenant_id": p["tenant_id"], "sku": p["sku"], "candidates": [s for _, s in cands[:5]]})
    store.write("substitutes", out)
    return out
