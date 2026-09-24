"""Catalogue vocabulary and seeded generation for the stylist's apparel line (DECISIONS §5.9).

Lives in its own tables (`apparel_products`, `apparel_stock`), never in `products`: the grocery
300-SKU invariants, the sell-by/gap pipeline and FORBIDDEN_WORDS stay untouched. Indian-context
garments and accessories across ~45 types; ~350 SKUs total. Everything here is invented.
"""
from __future__ import annotations

import json
import random
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from agents.stylist.colour import family_of

FESTIVALS = Path(__file__).resolve().parents[2] / "fixtures" / "festival_calendar.json"

STYLE_OCCASIONS: list[str] = ["casual", "office", "festive", "wedding", "party", "travel"]
STYLE_OCCASION_BASE_WEIGHTS: list[float] = [0.35, 0.15, 0.15, 0.10, 0.15, 0.10]
STYLE_SOURCES: list[str] = ["find_apparel", "suggest_pairings"]
STYLE_TIER_CHATTINESS: dict[str, float] = {"gold": 1.6, "silver": 1.1, "bronze": 0.6, "new": 0.3}
STYLE_HISTORY_DAYS = 70
N_HOT_NODES_PER_CLUSTER = 1
N_TRENDING_PAIRS_PER_CLUSTER = 2

# garment_type -> spec. role drives the pairing rules in agents/stylist/colour.py's ROLE_PAIRS.
# sections: which of women/men/unisex the type is cut for (affects sizing only, not who can pair).
GARMENTS: dict[str, dict[str, Any]] = {
    # tops
    "kurta": {"role": "top", "sections": ["women", "men"], "price": (350, 1800), "synonyms": ["kurti"]},
    "kurti": {"role": "top", "sections": ["women"], "price": (350, 1500), "synonyms": []},
    "saree blouse": {"role": "top", "sections": ["women"], "price": (250, 900), "synonyms": ["blouse"]},
    "t-shirt": {"role": "top", "sections": ["women", "men", "unisex"], "price": (250, 900), "synonyms": ["tee", "tshirt"]},
    "shirt": {"role": "top", "sections": ["women", "men"], "price": (400, 1500), "synonyms": []},
    "polo": {"role": "top", "sections": ["men", "unisex"], "price": (400, 1200), "synonyms": []},
    "crop top": {"role": "top", "sections": ["women"], "price": (300, 1000), "synonyms": []},
    "tunic": {"role": "top", "sections": ["women"], "price": (400, 1400), "synonyms": []},
    "sweatshirt": {"role": "top", "sections": ["unisex"], "price": (600, 1800), "synonyms": []},
    "hoodie": {"role": "top", "sections": ["unisex"], "price": (700, 2000), "synonyms": []},
    # bottoms
    "palazzo": {"role": "bottom", "sections": ["women"], "price": (350, 1200), "synonyms": []},
    "salwar": {"role": "bottom", "sections": ["women"], "price": (300, 1000), "synonyms": []},
    "churidar": {"role": "bottom", "sections": ["women"], "price": (300, 1000), "synonyms": []},
    "dhoti pants": {"role": "bottom", "sections": ["women", "men"], "price": (400, 1200), "synonyms": ["dhoti"]},
    "chinos": {"role": "bottom", "sections": ["men", "women"], "price": (700, 2200), "synonyms": []},
    "jeans": {"role": "bottom", "sections": ["women", "men", "unisex"], "price": (900, 3000), "synonyms": ["denims"]},
    "trousers": {"role": "bottom", "sections": ["women", "men"], "price": (600, 2000), "synonyms": ["pants"]},
    "shorts": {"role": "bottom", "sections": ["women", "men", "unisex"], "price": (400, 1200), "synonyms": []},
    "skirt": {"role": "bottom", "sections": ["women"], "price": (400, 1500), "synonyms": []},
    "leggings": {"role": "bottom", "sections": ["women"], "price": (250, 700), "synonyms": []},
    # dresses / one-piece
    "dress": {"role": "dress", "sections": ["women"], "price": (700, 3000), "synonyms": []},
    "anarkali": {"role": "dress", "sections": ["women"], "price": (1200, 5000), "synonyms": []},
    "saree": {"role": "dress", "sections": ["women"], "price": (1000, 6000), "synonyms": []},
    "lehenga set": {"role": "dress", "sections": ["women"], "price": (2500, 12000), "synonyms": ["lehenga"]},
    "jumpsuit": {"role": "dress", "sections": ["women"], "price": (900, 2800), "synonyms": []},
    "sherwani": {"role": "dress", "sections": ["men"], "price": (2500, 9000), "synonyms": []},
    "kurta set": {"role": "dress", "sections": ["women", "men"], "price": (900, 3500), "synonyms": []},
    # layers
    "dupatta": {"role": "layer", "sections": ["women"], "price": (300, 1500), "synonyms": []},
    "jacket": {"role": "layer", "sections": ["women", "men", "unisex"], "price": (900, 3500), "synonyms": []},
    "blazer": {"role": "layer", "sections": ["women", "men"], "price": (1500, 5000), "synonyms": []},
    "cardigan": {"role": "layer", "sections": ["women", "men", "unisex"], "price": (700, 2200), "synonyms": []},
    "nehru jacket": {"role": "layer", "sections": ["men"], "price": (1200, 4000), "synonyms": []},
    "shrug": {"role": "layer", "sections": ["women"], "price": (500, 1500), "synonyms": []},
    "stole": {"role": "layer", "sections": ["women", "unisex"], "price": (300, 1200), "synonyms": []},
    "sweater": {"role": "layer", "sections": ["women", "men", "unisex"], "price": (800, 2500), "synonyms": []},
    # footwear
    "sneakers": {"role": "footwear", "sections": ["women", "men", "unisex"], "price": (1200, 4500), "synonyms": ["shoes"]},
    "juttis": {"role": "footwear", "sections": ["women", "men"], "price": (500, 2000), "synonyms": []},
    "kolhapuris": {"role": "footwear", "sections": ["women", "men"], "price": (600, 2200), "synonyms": []},
    "sandals": {"role": "footwear", "sections": ["women", "men", "unisex"], "price": (400, 1800), "synonyms": []},
    "loafers": {"role": "footwear", "sections": ["women", "men"], "price": (1200, 3800), "synonyms": []},
    "heels": {"role": "footwear", "sections": ["women"], "price": (900, 3200), "synonyms": []},
    "boots": {"role": "footwear", "sections": ["women", "men", "unisex"], "price": (1500, 4800), "synonyms": []},
    "mojaris": {"role": "footwear", "sections": ["women", "men"], "price": (500, 1800), "synonyms": []},
    # accessories
    "scarf": {"role": "accessory", "sections": ["unisex"], "price": (200, 900), "synonyms": []},
    "belt": {"role": "accessory", "sections": ["unisex"], "price": (300, 1200), "synonyms": []},
    "earrings": {"role": "accessory", "sections": ["women"], "price": (150, 2500), "synonyms": [], "metal": True},
    "necklace": {"role": "accessory", "sections": ["women"], "price": (300, 4000), "synonyms": [], "metal": True},
    "bangles": {"role": "accessory", "sections": ["women"], "price": (200, 1800), "synonyms": [], "metal": True},
    "watch": {"role": "accessory", "sections": ["women", "men", "unisex"], "price": (900, 5000), "synonyms": [], "metal": True},
    "sunglasses": {"role": "accessory", "sections": ["unisex"], "price": (500, 2500), "synonyms": []},
    "handbag": {"role": "accessory", "sections": ["women"], "price": (700, 3500), "synonyms": ["bag"]},
    "tote": {"role": "accessory", "sections": ["women", "unisex"], "price": (500, 2200), "synonyms": []},
    "cap": {"role": "accessory", "sections": ["unisex"], "price": (250, 900), "synonyms": []},
    "clutch": {"role": "accessory", "sections": ["women"], "price": (400, 1800), "synonyms": []},
    "brooch": {"role": "accessory", "sections": ["women", "unisex"], "price": (150, 900), "synonyms": []},
}

ROLE_SIZES: dict[str, list[str]] = {
    "top": ["S", "M", "L", "XL", "XXL"], "bottom": ["S", "M", "L", "XL", "XXL"],
    "dress": ["S", "M", "L", "XL", "XXL"], "layer": ["S", "M", "L", "XL", "XXL"],
    "footwear": ["UK6", "UK7", "UK8", "UK9", "UK10"], "accessory": ["FREE"],
}

PATTERNS: list[str] = ["solid"] * 11 + ["floral", "striped", "checked", "block print", "ikat", "bandhani", "paisley", "embroidered", "kalamkari"]
FABRICS: list[str] = ["cotton", "linen", "silk", "chanderi", "chiffon", "georgette", "denim", "rayon", "polyester", "wool", "khadi", "crepe"]
FITS: list[str] = ["regular", "slim", "relaxed", "straight", "fitted"]
OCCASIONS: list[str] = ["casual", "office", "festive", "wedding", "party", "travel"]

# Colour words offered to the generator; every one must resolve via colour.family_of (asserted by
# tests/unit/test_apparel_generator.py). Metal words (gold/silver/rose gold/oxidised) are used only
# for garment types marked "metal": True above.
COLOUR_WORDS: list[str] = [
    "mustard", "maroon", "wine", "rust", "coral", "peach", "orange", "tangerine",
    "gold", "golden", "lemon", "olive", "lime", "green", "emerald", "mint", "sage",
    "teal", "turquoise", "blue", "cobalt", "royal blue", "sky blue", "indigo", "periwinkle",
    "purple", "violet", "lavender", "plum", "magenta", "pink", "fuchsia", "rani pink",
    "white", "off white", "cream", "ivory", "black", "charcoal", "silver", "grey",
    "beige", "tan", "khaki", "camel", "denim", "navy", "navy blue", "bottle green", "wine red",
]
METAL_WORDS: list[str] = ["gold", "silver", "rose gold", "oxidised"]

# Fixed-id planted SKUs: the demo anchor and the fixtures/tests that name them by id.
PLANTED_APPAREL: dict[str, dict[str, Any]] = {
    "APP-KURTA-MUSTARD-W": {"name": "Mustard Yellow Cotton Kurta", "garment_type": "kurta", "colour": "mustard yellow", "pattern": "solid", "fabric": "cotton", "section": "women", "occasions": ["casual", "festive"], "price": 899.0},
    "APP-TSHIRT-NAVY-U": {"name": "Navy Blue Crew T-Shirt", "garment_type": "t-shirt", "colour": "navy blue", "pattern": "solid", "fabric": "cotton", "section": "unisex", "occasions": ["casual", "travel"], "price": 499.0},
    "APP-DRESS-RED-FLORAL-W": {"name": "Red Floral Midi Dress", "garment_type": "dress", "colour": "wine red", "pattern": "floral", "fabric": "crepe", "section": "women", "occasions": ["party", "casual"], "price": 1799.0},
    "APP-PALAZZO-INDIGO-W": {"name": "Indigo Straight Palazzo", "garment_type": "palazzo", "colour": "indigo", "pattern": "solid", "fabric": "rayon", "section": "women", "occasions": ["casual", "festive"], "price": 799.0},
    "APP-CHINOS-BEIGE-M": {"name": "Beige Slim Chinos", "garment_type": "chinos", "colour": "beige", "pattern": "solid", "fabric": "cotton", "section": "men", "occasions": ["office", "casual"], "price": 1299.0},
    "APP-DUPATTA-TEAL-W": {"name": "Teal Chanderi Dupatta", "garment_type": "dupatta", "colour": "teal", "pattern": "solid", "fabric": "chanderi", "section": "women", "occasions": ["festive", "wedding"], "price": 649.0},
    "APP-JACKET-DENIM-U": {"name": "Denim Trucker Jacket", "garment_type": "jacket", "colour": "denim", "pattern": "solid", "fabric": "denim", "section": "unisex", "occasions": ["casual", "travel"], "price": 1999.0},
    "APP-SNEAKER-WHITE-U": {"name": "White Canvas Sneakers", "garment_type": "sneakers", "colour": "white", "pattern": "solid", "fabric": "canvas", "section": "unisex", "occasions": ["casual", "travel"], "price": 1799.0},
    "APP-JUTTI-TAN-W": {"name": "Tan Embroidered Juttis", "garment_type": "juttis", "colour": "tan", "pattern": "embroidered", "fabric": "leather", "section": "women", "occasions": ["festive", "wedding"], "price": 899.0},
    "APP-EARRING-GOLD-W": {"name": "Gold Jhumka Earrings", "garment_type": "earrings", "colour": "gold", "pattern": "solid", "fabric": "alloy", "section": "women", "occasions": ["festive", "wedding"], "price": 349.0, "metal": "gold"},
    "APP-BLAZER-BLACK-U": {"name": "Black Linen Blazer", "garment_type": "blazer", "colour": "black", "pattern": "solid", "fabric": "linen", "section": "unisex", "occasions": ["office", "party"], "price": 2999.0},
}

N_APPAREL_SKUS = 350
MIN_PER_GARMENT = 4
MAX_PER_GARMENT = 14


def _sku_id(garment: str, colour: str, section: str, n: int = 0) -> str:
    g = garment.upper().replace(" ", "-")
    c = colour.upper().replace(" ", "-")
    s = section[0].upper()
    suffix = f"-{n}" if n else ""
    return f"APP-{g}-{c}-{s}{suffix}"


def _row(rng: random.Random, tenant_id: str, sku: str, garment: str, colour: str, section: str) -> dict[str, Any]:
    spec = GARMENTS[garment]
    pattern = rng.choice(PATTERNS)
    is_metal = spec.get("metal")
    metal = rng.choice(METAL_WORDS) if is_metal else None
    colour_word = metal if is_metal else colour
    family = family_of(colour_word)
    assert family is not None, f"unresolved colour {colour_word!r} for {garment}"
    price = float(rng.randint(spec["price"][0] // 5, spec["price"][1] // 5) * 5)
    cost = round(price * rng.uniform(0.55, 0.75), 2)
    occasions = rng.sample(OCCASIONS, k=rng.randint(1, 3))
    return {
        "tenant_id": tenant_id, "sku": sku, "name": f"{colour_word.title()} {garment.title()}",
        "garment_type": garment, "role": spec["role"], "colour": colour_word, "colour_family": family,
        "pattern": pattern, "fabric": rng.choice(FABRICS), "fit": rng.choice(FITS),
        "occasions": occasions, "section": section, "metal": metal,
        "list_price": price, "unit_cost": cost, "season": rng.choice(["all-season", "summer", "winter", "festive"]),
    }


def generate_apparel(rng: random.Random, tenant_id: str, nodes: list[dict], as_of: date, n_skus: int = N_APPAREL_SKUS) -> tuple[list[dict], list[dict]]:
    """Deterministic apparel catalogue (~45 garment types, target n_skus rows) and per-(sku, node,
    size) stock at dark stores only. Planted SKUs come first with fixed prices; the rest fills a
    per-garment quota so every role and section is represented."""
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for sku, p in PLANTED_APPAREL.items():
        spec = GARMENTS[p["garment_type"]]
        colour_word = p.get("metal") or p["colour"]
        family = family_of(colour_word)
        assert family is not None, f"unresolved planted colour {colour_word!r}"
        rows.append({
            "tenant_id": tenant_id, "sku": sku, "name": p["name"], "garment_type": p["garment_type"],
            "role": spec["role"], "colour": p["colour"], "colour_family": family, "pattern": p["pattern"],
            "fabric": p["fabric"], "fit": "regular", "occasions": p["occasions"], "section": p["section"],
            "metal": p.get("metal"), "list_price": p["price"], "unit_cost": round(p["price"] * 0.65, 2),
            "season": "all-season",
        })
        seen.add(sku)

    garment_names = sorted(GARMENTS)
    counts: dict[str, int] = dict.fromkeys(garment_names, 0)
    for sku in PLANTED_APPAREL:
        counts[PLANTED_APPAREL[sku]["garment_type"]] += 1

    combos = [(g, c, s) for g in garment_names for c in COLOUR_WORDS for s in GARMENTS[g]["sections"]]
    rng.shuffle(combos)
    idx = 0
    # First pass: guarantee every garment type reaches MIN_PER_GARMENT.
    for garment, colour, section in combos:
        if len(rows) >= n_skus:
            break
        if counts[garment] >= MIN_PER_GARMENT:
            continue
        sku = _sku_id(garment, colour, section)
        n = 0
        while sku in seen:
            n += 1
            sku = _sku_id(garment, colour, section, n)
        seen.add(sku)
        rows.append(_row(rng, tenant_id, sku, garment, colour, section))
        counts[garment] += 1

    # Second pass: fill up to n_skus, respecting the per-garment cap.
    rng.shuffle(combos)
    while len(rows) < n_skus and idx < len(combos) * 4:
        garment, colour, section = combos[idx % len(combos)]
        idx += 1
        if counts[garment] >= MAX_PER_GARMENT:
            continue
        sku = _sku_id(garment, colour, section)
        n = 0
        while sku in seen:
            n += 1
            sku = _sku_id(garment, colour, section, n)
        seen.add(sku)
        rows.append(_row(rng, tenant_id, sku, garment, colour, section))
        counts[garment] += 1

    dark_stores = [n["node_id"] for n in nodes if n["type"] == "dark_store"]
    stock: list[dict[str, Any]] = []
    planted_ids = set(PLANTED_APPAREL)
    for row in rows:
        sizes = ROLE_SIZES[row["role"]]
        for node_id in dark_stores:
            empty = rng.random() < 0.25 and row["sku"] not in planted_ids
            # the black blazer is planted out of stock at DS-07 specifically, to exercise the
            # unfulfilled-ask path even though every other planted SKU is guaranteed in stock.
            if row["sku"] == "APP-BLAZER-BLACK-U" and node_id == "DS-07":
                empty = True
            if empty:
                continue
            for size in sizes:
                qty = rng.randint(2, 6) if row["sku"] in planted_ids else rng.randint(1, 6)
                stock.append({"tenant_id": tenant_id, "sku": row["sku"], "node_id": node_id, "size": size, "qty_on_hand": qty, "as_of": as_of.isoformat()})

    return rows, stock


def seed_style_requests(tenant_id: str, customers: list[dict], as_of: date) -> list[dict]:
    """Planted, deterministic history for the demo's assortment_gap (DECISIONS §5.9): three real
    DS-07 customers ask the stylist for a black blazer in the days before `as_of` and never get
    one -- APP-BLAZER-BLACK-U is deliberately out of stock at DS-07 (see the planted `empty=True`
    above) while DS-05 and DS-06, its own cluster-mates, carry it. jobs/sense/gaps.py's
    assortment_gap detection resolves this into a real, named gap the same way the grocery
    PLANTED_IDS scenarios are seeded, so the demo has one to show without waiting for a live
    stylist conversation to write it."""
    askers = sorted(c["customer_id"] for c in customers if c["home_node_id"] == "DS-07")[:8]
    rows = []
    for i, cid in enumerate(askers):
        ts = as_of - timedelta(days=1 + i)
        rows.append({
            "tenant_id": tenant_id, "customer_id": cid, "node_id": "DS-07",
            "session_id": f"{cid}:web", "ts": f"{ts.isoformat()}T{9 + (i % 10)}:00:00Z", "source": "find_apparel",
            "garment_type": "blazer", "colour": "black", "colour_family": "black", "occasion": "party" if i % 2 else "office",
            "query_text": "black blazer" if i % 2 else "do you have a black blazer for the office",
            "matched_sku": None, "fulfilled": False,
        })
    return rows


def _festival_windows(as_of: date, history_days: int) -> list[tuple[date, date]]:
    """(start, end) day ranges, clipped to the generation window, during which any festival in
    `fixtures/festival_calendar.json` is lifting demand. Reused as-is from the grocery generator's
    calendar: apparel does not need its own festival dates, only the same real-world lift window
    applied to festive/wedding occasion asks instead of sweets and snacks."""
    festivals = json.loads(FESTIVALS.read_text(encoding="utf-8"))["festivals"]
    start = as_of - timedelta(days=history_days)
    windows: list[tuple[date, date]] = []
    for f in festivals:
        fd = date.fromisoformat(f["date"])
        lo = max(start, fd - timedelta(days=f["window_days"]))
        hi = min(as_of, fd)
        if lo <= hi:
            windows.append((lo, hi))
    return windows


def generate_style_requests(
    rng: random.Random, tenant_id: str, customers: list[dict], nodes: list[dict],
    apparel_products: list[dict], apparel_stock: list[dict], as_of: date, history_days: int = STYLE_HISTORY_DAYS,
) -> list[dict]:
    """Simulated stylist asks across the same 70-day window and customer base the grocery
    generator uses, on its own RNG stream (never `self.rng`, so grocery and apparel-catalogue
    draws stay unaffected by this function existing or not).

    The rule, stated so it can be checked against the output:

    1. Every customer's home node is a dark store (apparel is dark-store-only stock), so every
       customer is a candidate asker. How often they ask over the window is `binomial(4, p)` where
       `p` scales with their RFM tier (`STYLE_TIER_CHATTINESS`: gold customers ask ~5x as often as
       new ones, mirroring the same tier-based engagement the grocery order-frequency rule uses)
       and with a x1.8 multiplier if their home node was picked (deterministically, from the run
       seed) as that node cluster's one "hot" dark store for the run -- concentration by node, so
       one store shows a visibly bigger local signal than its cluster-mates.
    2. Each cluster (north/south/east) is also seeded with `N_TRENDING_PAIRS_PER_CLUSTER`
       (garment_type, colour_family) pairs, drawn from the real apparel catalogue. Every ask in
       that cluster has a 55% chance of drawing one of its cluster's trending pairs and a 45%
       chance of drawing any catalogue pair uniformly -- this is what makes distinct trends emerge
       from aggregation (jobs/sense/trends.py) instead of uniform noise across ~45 garment types x
       12 colour families x 3 clusters.
    3. The occasion is drawn from `STYLE_OCCASION_BASE_WEIGHTS`, except that a day inside a real
       festival window (`fixtures/festival_calendar.json`, the same calendar the grocery generator
       already discloses) triples the relative weight of "festive" and "wedding" -- the same
       seasonality mechanism already used for sweets and snacks, applied to garments instead.
    4. Whether the ask is fulfilled is computed the same way `agents/stylist/tools.py::find_apparel`
       computes it live: does the customer's home node currently carry any in-stock sku of that
       (garment_type, colour_family)? If yes, `matched_sku` is that sku and `fulfilled=True`; if
       no, `matched_sku=None` and `fulfilled=False` -- a real, unfulfilled ask, exactly the signal
       `jobs/sense/gaps.py::_style_demand_signals` looks for.

    Nothing here is hand-placed to hit a row-count target: every row is a draw from this rule: only
    the RNG seed is fixed, for reproducibility, the same way every other seeded table in this
    generator is.
    """
    dark_store_nodes = [n for n in nodes if n["type"] == "dark_store"]
    clusters: dict[str, list[str]] = defaultdict(list)
    for n in dark_store_nodes:
        clusters[n["cluster_id"]].append(n["node_id"])

    hot_nodes: set[str] = set()
    for node_ids in (v for _, v in sorted(clusters.items())):
        hot_nodes.update(rng.sample(sorted(node_ids), k=min(N_HOT_NODES_PER_CLUSTER, len(node_ids))))

    combo_products: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for p in apparel_products:
        combo_products[(p["garment_type"], p["colour_family"])].append(p)
    all_combos = sorted(combo_products)

    cluster_trending: dict[str, list[tuple[str, str]]] = {}
    for cluster_id in sorted(clusters):
        cluster_trending[cluster_id] = rng.sample(all_combos, k=min(N_TRENDING_PAIRS_PER_CLUSTER, len(all_combos)))

    node_cluster: dict[str, str] = {n["node_id"]: n["cluster_id"] for n in dark_store_nodes}

    # sku -> (garment_type, colour_family), for the stock join below.
    sku_combo = {p["sku"]: (p["garment_type"], p["colour_family"]) for p in apparel_products}
    in_stock = defaultdict(set)
    for r in apparel_stock:
        if int(r["qty_on_hand"]) <= 0:
            continue
        combo = sku_combo.get(r["sku"])
        if combo:
            in_stock[(r["node_id"], *combo)].add(r["sku"])

    festival_windows = _festival_windows(as_of, history_days)
    start = as_of - timedelta(days=history_days)

    def _is_festival_day(d: date) -> bool:
        return any(lo <= d <= hi for lo, hi in festival_windows)

    rows: list[dict[str, Any]] = []
    for c in customers:
        node_id = c["home_node_id"]
        cluster_id = node_cluster.get(node_id)
        if cluster_id is None:
            continue  # customer homed to an outlet: apparel has no outlet stock to ask about
        p = 0.028 * STYLE_TIER_CHATTINESS.get(c["rfm_tier"], 0.5) * (1.8 if node_id in hot_nodes else 1.0)
        n_asks = sum(1 for _ in range(4) if rng.random() < p)
        for _ in range(n_asks):
            day_offset = rng.randint(0, history_days - 1)
            d = start + timedelta(days=day_offset)
            if rng.random() < 0.55 and cluster_trending[cluster_id]:
                garment_type, colour_family = rng.choice(cluster_trending[cluster_id])
            else:
                garment_type, colour_family = rng.choice(all_combos)
            weights = list(STYLE_OCCASION_BASE_WEIGHTS)
            if _is_festival_day(d):
                for i, occ in enumerate(STYLE_OCCASIONS):
                    if occ in ("festive", "wedding"):
                        weights[i] *= 3.0
            occasion = rng.choices(STYLE_OCCASIONS, weights=weights)[0]
            product = rng.choice(combo_products[(garment_type, colour_family)])
            colour_word = product["colour"]
            candidates = in_stock.get((node_id, garment_type, colour_family), set())
            fulfilled = bool(candidates)
            matched_sku = sorted(candidates)[0] if candidates else None
            source = rng.choices(STYLE_SOURCES, weights=[0.65, 0.35])[0]
            query_text = f"any {colour_word} {garment_type} for {occasion}?" if source == "find_apparel" else f"what goes with a {colour_word} {garment_type}"
            hour = rng.randint(8, 21)
            minute = rng.randint(0, 59)
            rows.append({
                "tenant_id": tenant_id, "customer_id": c["customer_id"], "node_id": node_id,
                "session_id": f"{c['customer_id']}:web", "ts": f"{d.isoformat()}T{hour:02d}:{minute:02d}:00Z",
                "source": source, "garment_type": garment_type, "colour": colour_word, "colour_family": colour_family,
                "occasion": occasion, "query_text": query_text, "matched_sku": matched_sku, "fulfilled": fulfilled,
            })
    rows.sort(key=lambda r: r["ts"])
    return rows
