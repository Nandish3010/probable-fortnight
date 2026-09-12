"""Derive affinity, segment features and coupon-response priors from The Complete Journey.

Runs only when data/public/raw/ contains the licensed CSVs; writes derived aggregates only (never
raw rows) into TAAL_DATA_DIR. The mapping to the demo tenant is by category, not by product, so no
household or product row from the licensed data is reproduced.
"""
from __future__ import annotations

import csv
import os
import sys
from collections import defaultdict
from pathlib import Path

from agents.gate.store import LocalStore

RAW = Path(__file__).resolve().parent / "raw"
REQUIRED = ("transaction_data.csv", "coupon_redempt.csv", "coupon.csv", "campaign_table.csv", "product.csv")


def coupon_response_priors(raw: Path) -> dict[str, tuple[float, float, int]]:
    """Beta(alpha, beta) per department from campaign exposure vs redemption, capped at a pseudo-count
    of 200 so the prior stays weak (DECISIONS §3.4)."""
    campaigns_per_household: dict[str, int] = defaultdict(int)
    with open(raw / "campaign_table.csv", newline="") as f:
        for r in csv.DictReader(f):
            campaigns_per_household[r["household_key"]] += 1
    dept_of_product: dict[str, str] = {}
    with open(raw / "product.csv", newline="") as f:
        for r in csv.DictReader(f):
            dept_of_product[r["PRODUCT_ID"]] = r["DEPARTMENT"].strip().lower()
    coupon_dept: dict[str, str] = {}
    with open(raw / "coupon.csv", newline="") as f:
        for r in csv.DictReader(f):
            coupon_dept.setdefault(r["COUPON_UPC"], dept_of_product.get(r["PRODUCT_ID"], "other"))
    redeemed: dict[str, int] = defaultdict(int)
    with open(raw / "coupon_redempt.csv", newline="") as f:
        for r in csv.DictReader(f):
            redeemed[coupon_dept.get(r["COUPON_UPC"], "other")] += 1
    exposures = sum(campaigns_per_household.values()) or 1
    out = {}
    for dept, n in redeemed.items():
        rate = min(0.5, n / exposures)
        pseudo = 200.0
        out[dept] = (max(1.0, rate * pseudo), max(1.0, (1 - rate) * pseudo), n)
    return out


def main() -> int:
    if not RAW.exists() or not all((RAW / f).exists() for f in REQUIRED):
        print("transform_complete_journey: data/public/raw is missing the licensed files; nothing done")
        return 0
    store = LocalStore(os.environ.get("TAAL_DATA_DIR", ".local/data"))
    priors = coupon_response_priors(RAW)
    rows = store.read("estimator_priors")
    dept_to_category = {"grocery": "staples", "produce": "staples", "deli": "bakery", "pastry": "bakery", "drug gm": "personal_care", "meat": "dairy"}
    for r in rows:
        if r["mechanic"] != "coupon":
            continue
        for dept, (a, b, _n) in priors.items():
            if dept_to_category.get(dept) == r["category"]:
                r["alpha"], r["beta"], r["n_measured"], r["source"] = round(a, 2), round(b, 2), 0, f"complete_journey:{dept}"
    store.write("estimator_priors", rows)
    print(f"transform_complete_journey: priors updated for {len(priors)} departments (derived aggregates only)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
