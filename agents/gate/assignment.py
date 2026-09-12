"""Holdout assignment (DECISIONS §5.4): stable hash of customer_id and seed, no randomness.

Local stand-in for BigQuery `FARM_FINGERPRINT(customer_id || seed)`: sha256 of
"{customer_id}|{seed}" taken modulo 10,000; a customer is holdout when the bucket is below
`holdout_fraction * 10000`, so the fraction is honoured to 0.01% resolution and every service
(assignment, apply_offer, proactive delivery) reproduces the same arm from the seed.
"""
from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any, Literal

Arm = Literal["treated", "holdout"]
BUCKETS = 10_000


def bucket(customer_id: str, seed: str) -> int:
    digest = hashlib.sha256(f"{customer_id}|{seed}".encode()).digest()
    return int.from_bytes(digest[:8], "big") % BUCKETS


def assign_arm(customer_id: str, seed: str, holdout_fraction: float) -> Arm:
    if not 0.0 <= holdout_fraction <= 1.0:
        raise ValueError("holdout_fraction must lie in [0, 1]")
    threshold = int(round(holdout_fraction * BUCKETS))
    return "holdout" if bucket(customer_id, seed) < threshold else "treated"


def assign(play: dict[str, Any], customer_ids: list[str], assigned_at: str | None = None) -> list[dict[str, Any]]:
    """play_assignments rows for one play. Idempotent: the same play and ids give the same rows
    (bar `assigned_at`, which the caller may pin)."""
    holdout = play["holdout"]
    seed, fraction, play_id = str(holdout["seed"]), float(holdout["fraction"]), play["play_id"]
    ts = assigned_at or datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    seen: set[str] = set()
    rows = []
    for cid in customer_ids:
        if cid in seen:
            continue
        seen.add(cid)
        rows.append({"play_id": play_id, "customer_id": cid, "arm": assign_arm(cid, seed, fraction), "assigned_at": ts})
    return rows
