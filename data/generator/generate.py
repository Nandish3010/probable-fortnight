"""Seeded synthetic Indian layer for the demo tenant (DECISIONS §3.2). Emits the exact DDL schema
under data/bigquery/ddl as JSONL tables in TAAL_DATA_DIR (LocalStore), plus manifest.json.

Determinism: one `random.Random(seed)`, a fixed `as_of` date, no wall-clock reads, insertion-
ordered dicts. Two runs with the same seed are byte-identical (tests/unit/test_generator.py).

Daily sales rule (stated so it can be checked): for each sku the weekly total at a typical node
is velocity(category) x popularity(sku) x 7; it is spread to nodes by fixed node shares, to days
by the day-of-week profile, lifted by festival windows and promo days, then multiplied by
lognormal noise (sigma 0.25) and rounded to an integer.

Planted situations (fixed ids, asserted by tests and used by the demo script):
  chips lot at DS-07 six days from online sell-by (B-CHIPS-DS07-01), Cola Zero stockout at
  DS-07 and DS-02, Kaju Katli festival stockout at DS-01 and DS-03, Quinoa slow mover at
  OUT-02, Darjeeling tea lot at DS-04 for the policy beat.
"""
from __future__ import annotations

import hashlib
import json
import math
import random
from datetime import date, timedelta
from pathlib import Path

from agents.gate.config import TenantConfig, load_tenant
from agents.gate.sellby import online_sellby_date
from agents.gate.store import LocalStore

from .catalog import (
    CATEGORIES,
    CATEGORY_VELOCITY,
    DAY_OF_WEEK_PROFILE,
    FORBIDDEN_WORDS,
    PLANTED_SKUS,
)

AS_OF = date(2026, 9, 12)
HISTORY_DAYS = 70
N_SKUS = 300
N_CUSTOMERS = 4000
DARK_STORES = [f"DS-{i:02d}" for i in range(1, 11)]
OUTLETS = [f"OUT-{i:02d}" for i in range(1, 7)]
CLUSTERS = {"north": DARK_STORES[0:4] + OUTLETS[0:2], "south": DARK_STORES[4:7] + OUTLETS[2:4], "east": DARK_STORES[7:10] + OUTLETS[4:6]}
FESTIVALS = Path(__file__).resolve().parents[2] / "fixtures" / "festival_calendar.json"

MEENA = "CUST-MEENA"
RAVI = "CUST-RAVI"


def _iso(d: date) -> str:
    return d.isoformat()


def _ts(d: date, hour: int = 10, minute: int = 0) -> str:
    return f"{d.isoformat()}T{hour:02d}:{minute:02d}:00Z"


class Generator:
    def __init__(self, seed: int, tenant: TenantConfig | None = None):
        self.seed = seed
        self.rng = random.Random(seed)
        self.tenant = tenant or load_tenant()
        self.tid = self.tenant.tenant_id
        self.festivals = json.loads(FESTIVALS.read_text(encoding="utf-8"))["festivals"]

    # ------------------------------------------------------------------ catalogue
    def products(self) -> list[dict]:
        rng = self.rng
        rows: list[dict] = []
        for sku, p in PLANTED_SKUS.items():
            rows.append({"tenant_id": self.tid, "sku": sku, **p, "margin_floor_pct": self.tenant.margin_floor(p["category"])})
        seen = {r["sku"] for r in rows}
        combos = [(cat, base, pack) for cat, spec in CATEGORIES.items() for base in spec["items"] for pack in spec["packs"]]
        rng.shuffle(combos)
        for cat, base, pack in combos:
            if len(rows) >= N_SKUS:
                break
            spec = CATEGORIES[cat]
            sku = "SKU-" + base.upper().replace(" ", "-") + "-" + pack
            if sku in seen:
                continue
            seen.add(sku)
            price = float(rng.randint(spec["price"][0] // 5, spec["price"][1] // 5) * 5)
            cost = round(price * rng.uniform(*spec["cost_frac"]), 2)
            grams = int("".join(ch for ch in pack if ch.isdigit()))
            if pack.endswith("KG") or pack.endswith("L"):
                grams *= 1000
            rows.append({
                "tenant_id": self.tid, "sku": sku, "name": f"{base} {pack}", "category": cat, "pack_size": pack,
                "pack_weight_g": grams, "unit_cost": cost, "list_price": price,
                "margin_floor_pct": self.tenant.margin_floor(cat),
                "shelf_life_days": rng.randint(*spec["shelf_life"]), "is_food": spec["is_food"],
            })
        for r in rows:
            low = r["name"].lower()
            assert not any(w in low for w in FORBIDDEN_WORDS), r
        return rows

    def nodes(self) -> list[dict]:
        rows = []
        for cluster, ids in CLUSTERS.items():
            for i, node_id in enumerate(ids):
                is_ds = node_id.startswith("DS")
                rows.append({
                    "tenant_id": self.tid, "node_id": node_id,
                    "name": f"{'Dark store' if is_ds else 'Outlet'} {node_id[-2:]} ({cluster.title()} Bengaluru)",
                    "type": "dark_store" if is_ds else "outlet",
                    "lat": round(12.90 + 0.04 * list(CLUSTERS).index(cluster) + 0.012 * i, 4),
                    "lng": round(77.55 + 0.03 * list(CLUSTERS).index(cluster) + 0.009 * i, 4),
                    "lead_time_days": 3 if is_ds else 5, "cluster_id": cluster,
                })
        return rows

    # ------------------------------------------------------------------ demand model
    def _popularity(self, products: list[dict]) -> dict[str, float]:
        pop = {}
        for p in products:
            pop[p["sku"]] = self.rng.lognormvariate(0.0, 0.5)
        pop["SKU-MASALA-CHIPS-200G"] = 1.4
        pop["SKU-COLA-ZERO-500ML"] = 1.8
        pop["SKU-COLA-LITE-500ML"] = 1.2
        pop["SKU-KAJU-KATLI-250G"] = 1.6
        pop["SKU-DARJEELING-TEA-100G"] = 0.7
        pop["SKU-QUINOA-500G"] = 0.08
        return pop

    def _node_share(self, nodes: list[dict]) -> dict[str, float]:
        raw = {n["node_id"]: (1.0 if n["type"] == "dark_store" else 0.55) * self.rng.uniform(0.7, 1.3) for n in nodes}
        total = sum(raw.values())
        return {k: v / total for k, v in raw.items()}

    def _festival_lift(self, d: date, category: str) -> float:
        lift = 1.0
        for f in self.festivals:
            fd = date.fromisoformat(f["date"])
            if category in f["categories"] and fd - timedelta(days=f["window_days"]) <= d <= fd:
                lift = max(lift, 1.0 + 0.6 * (1 - (fd - d).days / max(1, f["window_days"])))
        return lift

    def daily_rate(self, product: dict, node: dict, d: date, popularity: float, share: float, n_nodes: int) -> float:
        weekly_sku_total = CATEGORY_VELOCITY[product["category"]] * popularity * 7 * n_nodes * 0.85
        base = weekly_sku_total * share * DAY_OF_WEEK_PROFILE[d.weekday()] / 7.0
        return base * self._festival_lift(d, product["category"])

    def sales_daily(self, products: list[dict], nodes: list[dict]) -> tuple[list[dict], dict[str, dict[str, float]]]:
        rng = self.rng
        pop = self._popularity(products)
        share = self._node_share(nodes)
        rows: list[dict] = []
        mean_rate: dict[str, dict[str, float]] = {}
        start = AS_OF - timedelta(days=HISTORY_DAYS)
        days = [start + timedelta(days=i) for i in range(HISTORY_DAYS)]
        for p in products:
            promo_days = set(rng.sample(range(HISTORY_DAYS), 4))
            for n in nodes:
                acc = 0.0
                for i, d in enumerate(days):
                    rate = self.daily_rate(p, n, d, pop[p["sku"]], share[n["node_id"]], len(nodes))
                    on_promo = i in promo_days
                    if on_promo:
                        rate *= 1.5
                    units = int(round(rate * rng.lognormvariate(0.0, 0.25)))
                    acc += rate
                    if units <= 0:
                        continue
                    price = p["list_price"] * (0.85 if on_promo else 1.0)
                    rows.append({"tenant_id": self.tid, "date": _iso(d), "sku": p["sku"], "node_id": n["node_id"], "units": units, "revenue": round(units * price, 2), "on_promo": on_promo})
                mean_rate.setdefault(p["sku"], {})[n["node_id"]] = acc / HISTORY_DAYS
        return rows, mean_rate

    # ------------------------------------------------------------------ stock
    def batches_and_inbound(self, products: list[dict], nodes: list[dict], mean_rate: dict[str, dict[str, float]]) -> tuple[list[dict], list[dict]]:
        rng = self.rng
        rule = self.tenant.sellby_rule
        batches: list[dict] = []
        inbound: list[dict] = []
        planted = {("SKU-MASALA-CHIPS-200G", "DS-07"), ("SKU-COLA-ZERO-500ML", "DS-07"), ("SKU-COLA-ZERO-500ML", "DS-02"), ("SKU-KAJU-KATLI-250G", "DS-01"), ("SKU-KAJU-KATLI-250G", "DS-03"), ("SKU-QUINOA-500G", "OUT-02"), ("SKU-DARJEELING-TEA-100G", "DS-04")}
        by_sku = {p["sku"]: p for p in products}

        def add_batch(batch_id: str, sku: str, node_id: str, qty: int, expiry: date, received: date) -> None:
            p = by_sku[sku]
            batches.append({
                "tenant_id": self.tid, "batch_id": batch_id, "sku": sku, "node_id": node_id, "qty_on_hand": qty,
                "expiry_date": _iso(expiry), "online_sellby_date": _iso(online_sellby_date(expiry, p["shelf_life_days"], rule, p["is_food"])),
                "received_at": _iso(received), "source": "system", "capture_ref": None, "sellby_rule_version": rule.version,
            })

        for p in products:
            for n in nodes:
                key = (p["sku"], n["node_id"])
                if key in planted:
                    continue
                rate = mean_rate[p["sku"]][n["node_id"]]
                cover_days = rng.uniform(6, 16)
                qty = max(0, int(round(rate * cover_days)))
                if qty == 0 and rng.random() < 0.6:
                    continue
                age = rng.randint(1, max(2, p["shelf_life_days"] // 3))
                received = AS_OF - timedelta(days=age)
                expiry = received + timedelta(days=p["shelf_life_days"])
                add_batch(f"B-{p['sku'][4:]}-{n['node_id']}-01", p["sku"], n["node_id"], qty, expiry, received)
                if rng.random() < 0.35:
                    inbound.append({"tenant_id": self.tid, "po_id": f"PO-{p['sku'][4:]}-{n['node_id']}", "sku": p["sku"], "node_id": n["node_id"], "qty": max(1, int(round(rate * rng.uniform(5, 12)))), "eta": _iso(AS_OF + timedelta(days=rng.randint(1, 7)))})

        # Planted: chips lot at DS-07. Shelf life 90 days -> cut-off 27 days under the "either" rule;
        # expiry in 33 days puts the online sell-by 6 days out.
        add_batch("B-CHIPS-DS07-01", "SKU-MASALA-CHIPS-200G", "DS-07", 440, AS_OF + timedelta(days=33), AS_OF - timedelta(days=57))
        # Planted: Cola Zero stockout at DS-07 and DS-02 (empty shelf, inbound after lead time).
        add_batch("B-COLAZERO-DS07-01", "SKU-COLA-ZERO-500ML", "DS-07", 0, AS_OF + timedelta(days=120), AS_OF - timedelta(days=30))
        add_batch("B-COLAZERO-DS02-01", "SKU-COLA-ZERO-500ML", "DS-02", 3, AS_OF + timedelta(days=120), AS_OF - timedelta(days=30))
        for node_id in ("DS-07", "DS-02"):
            inbound.append({"tenant_id": self.tid, "po_id": f"PO-COLAZERO-{node_id}", "sku": "SKU-COLA-ZERO-500ML", "node_id": node_id, "qty": 120, "eta": _iso(AS_OF + timedelta(days=9))})
        # Planted: festival sweets short at DS-01 and DS-03 over the lead time.
        for node_id in ("DS-01", "DS-03"):
            add_batch(f"B-KAJU-{node_id}-01", "SKU-KAJU-KATLI-250G", node_id, 6, AS_OF + timedelta(days=22), AS_OF - timedelta(days=8))
            inbound.append({"tenant_id": self.tid, "po_id": f"PO-KAJU-{node_id}", "sku": "SKU-KAJU-KATLI-250G", "node_id": node_id, "qty": 80, "eta": _iso(AS_OF + timedelta(days=10))})
        # Planted: slow mover at OUT-02.
        add_batch("B-QUINOA-OUT02-01", "SKU-QUINOA-500G", "OUT-02", 60, AS_OF + timedelta(days=300), AS_OF - timedelta(days=65))
        # Planted: premium tea lot at DS-04. Shelf life 365 days -> cut-off 45 days; expiry in 69
        # days puts the online sell-by 24 days out.
        add_batch("B-TEA-DS04-01", "SKU-DARJEELING-TEA-100G", "DS-04", 120, AS_OF + timedelta(days=69), AS_OF - timedelta(days=296))
        return batches, inbound

    # ------------------------------------------------------------------ customers
    def customers_consent_affinity(self, products: list[dict], nodes: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
        rng = self.rng
        customers: list[dict] = []
        consent: list[dict] = []
        affinity: list[dict] = []
        by_cat: dict[str, list[dict]] = {}
        for p in products:
            by_cat.setdefault(p["category"], []).append(p)
        first = ["Meena", "Ravi", "Anjali", "Suresh", "Priya", "Kiran", "Lakshmi", "Arun", "Deepa", "Manoj", "Kavya", "Naveen", "Shruti", "Vikram", "Pooja", "Harish", "Divya", "Rohit", "Sneha", "Ganesh"]
        subscribable = [p["sku"] for p in products if p["category"] in ("staples", "dairy")]
        fixed = [
            (MEENA, "DS-07", "kn", "gold", ["snacks", "beverages", "dairy"]),
            (RAVI, "DS-04", "en", "silver", ["premium_tea", "staples"]),
        ]
        for i in range(N_CUSTOMERS):
            if i < len(fixed):
                cid, home, lang, tier, likes = fixed[i]
                subs: list[str] = []
            else:
                cid = f"CUST-{i:05d}"
                home = DARK_STORES[i % len(DARK_STORES)]
                lang = "kn" if rng.random() < 0.3 else "en"
                tier = rng.choices(["gold", "silver", "bronze", "new"], [0.15, 0.3, 0.4, 0.15])[0]
                likes = rng.sample(list(by_cat), k=rng.randint(2, 4))
                subs = rng.sample(subscribable, k=rng.randint(1, 2)) if rng.random() < 0.08 else []
                if rng.random() < 0.01:
                    subs.append("SKU-MASALA-CHIPS-200G")
            customers.append({"tenant_id": self.tid, "customer_id": cid, "display_name": first[i % len(first)] if i >= len(fixed) else cid[5:].title(), "home_node_id": home, "language": lang, "rfm_tier": tier, "segment_id": None, "subscription_skus": subs, "created_at": _iso(AS_OF - timedelta(days=rng.randint(30, 700)))})
            granted = True if i < len(fixed) else rng.random() < 0.85
            consent.append({"tenant_id": self.tid, "customer_id": cid, "channel": "web_chat", "purpose": "marketing", "source": "app_signup", "ts": _ts(AS_OF - timedelta(days=rng.randint(10, 400))), "withdrawn_at": None if granted else _ts(AS_OF - timedelta(days=rng.randint(1, 9)))})
            for cat in likes:
                picks = rng.sample(by_cat[cat], k=min(len(by_cat[cat]), rng.randint(3, 6)))
                for p in picks:
                    affinity.append({"tenant_id": self.tid, "customer_id": cid, "sku": p["sku"], "score": round(rng.uniform(0.3, 0.95), 3)})
            if "snacks" in likes and rng.random() < 0.7:
                affinity.append({"tenant_id": self.tid, "customer_id": cid, "sku": "SKU-MASALA-CHIPS-200G", "score": round(rng.uniform(0.5, 0.95), 3)})
            if "beverages" in likes and rng.random() < 0.6:
                affinity.append({"tenant_id": self.tid, "customer_id": cid, "sku": "SKU-COLA-ZERO-500ML", "score": round(rng.uniform(0.5, 0.95), 3)})
        affinity.append({"tenant_id": self.tid, "customer_id": MEENA, "sku": "SKU-MASALA-CHIPS-200G", "score": 0.91})
        affinity.append({"tenant_id": self.tid, "customer_id": MEENA, "sku": "SKU-COLA-ZERO-500ML", "score": 0.88})
        affinity.append({"tenant_id": self.tid, "customer_id": RAVI, "sku": "SKU-DARJEELING-TEA-100G", "score": 0.9})
        # dedupe (customer, sku), keep first
        seen: set[tuple[str, str]] = set()
        deduped = []
        for a in affinity:
            k = (a["customer_id"], a["sku"])
            if k in seen:
                continue
            seen.add(k)
            deduped.append(a)
        return customers, consent, deduped

    def orders(self, customers: list[dict], affinity: list[dict], products: list[dict]) -> tuple[list[dict], list[dict]]:
        rng = self.rng
        by_sku = {p["sku"]: p for p in products}
        aff: dict[str, list[str]] = {}
        for a in affinity:
            aff.setdefault(a["customer_id"], []).append(a["sku"])
        freq = {"gold": 9, "silver": 5, "bronze": 3, "new": 1}
        orders: list[dict] = []
        lines: list[dict] = []
        for c in customers:
            n_orders = max(0, int(round(freq[c["rfm_tier"]] * rng.uniform(0.6, 1.4))))
            for k in range(n_orders):
                d = AS_OF - timedelta(days=rng.randint(1, HISTORY_DAYS - 1))
                order_id = f"ORD-{c['customer_id'][5:]}-{k:02d}"
                skus = rng.sample(aff.get(c["customer_id"], ["SKU-MASALA-CHIPS-200G"]), k=min(len(aff.get(c["customer_id"], [1])), rng.randint(1, 4)))
                total = 0.0
                ts = _ts(d, rng.randint(8, 21), rng.randint(0, 59))
                for ln, sku in enumerate(skus, start=1):
                    qty = rng.choices([1, 2, 3], [0.7, 0.22, 0.08])[0]
                    price = by_sku[sku]["list_price"]
                    lines.append({"tenant_id": self.tid, "order_id": order_id, "line_no": ln, "customer_id": c["customer_id"], "node_id": c["home_node_id"], "sku": sku, "qty": qty, "price": price, "discount": 0.0, "play_id": None, "ts": ts})
                    total += qty * price
                orders.append({"tenant_id": self.tid, "order_id": order_id, "customer_id": c["customer_id"], "node_id": c["home_node_id"], "channel": "app", "ts": ts, "total_inr": round(total, 2)})
        return orders, lines

    def future_regressors(self, products: list[dict]) -> list[dict]:
        """Nightly regressor table: festival flags per sku x cluster for the next 28 days; on_promo
        is filled by approved plays (services/api/approve.py)."""
        rows = []
        for i in range(28):
            d = AS_OF + timedelta(days=i)
            for p in products:
                fest = None
                for f in self.festivals:
                    fd = date.fromisoformat(f["date"])
                    if p["category"] in f["categories"] and fd - timedelta(days=f["window_days"]) <= d <= fd:
                        fest = f["name"]
                for cluster in CLUSTERS:
                    rows.append({"tenant_id": self.tid, "date": _iso(d), "sku": p["sku"], "cluster_id": cluster, "on_promo": False, "is_festival": fest is not None, "festival_name": fest, "play_id": None})
        return rows

    def priors(self) -> list[dict]:
        """Weak, disclosed priors: alpha=1, beta=19 (5%) for every mechanic x category; nothing measured yet."""
        rows = []
        for mech in ("bundle", "usual_order_addon", "substitution", "preorder", "subscription_nudge", "coupon", "outlet_markdown", "transfer_plus_nudge"):
            for cat in CATEGORIES:
                rows.append({"tenant_id": self.tid, "mechanic": mech, "category": cat, "segment_id": "*", "alpha": 1.0, "beta": 19.0, "n_measured": 0, "updated_at": _ts(AS_OF)})
        return rows

    # ------------------------------------------------------------------ run
    def run(self, out: str | Path) -> dict:
        store = LocalStore(out)
        products = self.products()
        nodes = self.nodes()
        sales, mean_rate = self.sales_daily(products, nodes)
        batches, inbound = self.batches_and_inbound(products, nodes, mean_rate)
        customers, consent, affinity = self.customers_consent_affinity(products, nodes)
        orders, lines = self.orders(customers, affinity, products)
        regressors = self.future_regressors(products)
        tables = {
            "products": products, "nodes": nodes, "sales_daily": sales, "inventory_batches": batches, "inbound": inbound,
            "customers": customers, "consent": consent, "affinity": affinity, "orders": orders, "order_lines": lines,
            "future_regressors": regressors, "estimator_priors": self.priors(),
        }
        for name, rows in tables.items():
            store.write(name, rows)
        manifest = {
            "tenant_id": self.tid, "seed": self.seed, "as_of": _iso(AS_OF), "history_days": HISTORY_DAYS,
            "sellby_rule": self.tenant.sellby_rule.version,
            "counts": {k: len(v) for k, v in tables.items()},
            "sha256": {k: hashlib.sha256((store.root / f"{k}.jsonl").read_bytes()).hexdigest() for k in tables},
            "planted": {
                "gap_chips_ds07": {"sku": "SKU-MASALA-CHIPS-200G", "node_id": "DS-07", "batch_id": "B-CHIPS-DS07-01"},
                "stockout_cola_zero": {"sku": "SKU-COLA-ZERO-500ML", "node_ids": ["DS-07", "DS-02"]},
                "stockout_kaju_katli": {"sku": "SKU-KAJU-KATLI-250G", "node_ids": ["DS-01", "DS-03"]},
                "slow_mover_quinoa": {"sku": "SKU-QUINOA-500G", "node_id": "OUT-02"},
                "gap_tea_ds04": {"sku": "SKU-DARJEELING-TEA-100G", "node_id": "DS-04", "batch_id": "B-TEA-DS04-01"},
            },
        }
        (store.root / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return manifest


def generate(out: str | Path, seed: int = 20260912) -> dict:
    return Generator(seed).run(out)


def sales_total(rows: list[dict]) -> int:
    return int(math.fsum(r["units"] for r in rows))
