"""Runtime invariant (DECISIONS SS17.5): before a play is written, an independently-written
recomputation of its headline money numbers (margin, discount cost, waste avoided) from the
play's own raw fields -- never by calling agents.gate.estimator -- must agree with what the play
itself reports. This mirrors the independent SQL recomputation of gap rupees_at_stake
(data/bigquery/assertions/gap_rupees_recompute.sql): the same documented formula, re-typed by
hand in a separate code path, so a bug in one implementation's arithmetic (a dropped term, a
sign flip, a unit mismatch) does not get compared against itself and pass silently.
"""
from __future__ import annotations

from typing import Any

TOLERANCE_INR = 1.0


def recompute_play_money(
    play: dict[str, Any],
    unit_cost: float,
    list_price: float,
    units_at_risk: int,
    bundle_partner_unit_cost: float = 0.0,
    bundle_partner_list_price: float = 0.0,
    transfer_cost_per_unit: float = 2.0,
) -> dict[str, float]:
    """Margin, discount cost and waste avoided for `play`, recomputed from its own units and
    mechanic params plus product economics -- the same formulas documented in estimator.py's
    module docstring, independently re-typed here."""
    units = float((play.get("expected_outcome") or {}).get("units") or 0.0)
    mechanic = play.get("mechanic")
    params = play.get("mechanic_params") or {}
    waste_avoided = min(units, units_at_risk) * unit_cost

    if mechanic in ("coupon", "outlet_markdown"):
        pct = float(params.get("discount_pct" if mechanic == "coupon" else "markdown_pct", 0) or 0)
        discount = list_price * pct / 100.0
        margin = units * (list_price - discount - unit_cost)
        discount_cost = units * discount
    elif mechanic == "bundle":
        bundle_price = float(params.get("bundle_price", 0) or 0)
        margin = units * (bundle_price - unit_cost - bundle_partner_unit_cost)
        discount_cost = units * max(0.0, list_price + bundle_partner_list_price - bundle_price)
    elif mechanic == "transfer_plus_nudge":
        transfer_units = float(params.get("transfer_units", units_at_risk) or units_at_risk)
        margin = waste_avoided - transfer_cost_per_unit * transfer_units
        discount_cost = 0.0
    else:
        margin = units * (list_price - unit_cost)
        discount_cost = 0.0

    return {
        "margin_inr": round(margin, 2),
        "discount_cost_inr": round(discount_cost, 2),
        "waste_avoided_inr": round(waste_avoided, 2),
    }


def check_play_money(
    play: dict[str, Any],
    unit_cost: float,
    list_price: float,
    units_at_risk: int,
    bundle_partner_unit_cost: float = 0.0,
    bundle_partner_list_price: float = 0.0,
    transfer_cost_per_unit: float = 2.0,
    tolerance_inr: float = TOLERANCE_INR,
) -> list[str]:
    """Mismatch descriptions between `play["expected_outcome"]` and the independent
    recomputation; empty means they agree within `tolerance_inr`. Callers that write plays
    (agents/planner/tools.py::propose_play) block the write when this is non-empty."""
    recomputed = recompute_play_money(play, unit_cost, list_price, units_at_risk, bundle_partner_unit_cost, bundle_partner_list_price, transfer_cost_per_unit)
    reported = play.get("expected_outcome") or {}
    problems = []
    for key, label in (("margin_inr", "margin_inr"), ("discount_cost_inr", "discount_cost_inr"), ("waste_avoided_inr", "waste_avoided_inr")):
        got = reported.get(key)
        want = recomputed[key]
        if got is None or not isinstance(got, int | float) or isinstance(got, bool) or abs(float(got) - want) > tolerance_inr:
            problems.append(f"{label}: play reports {got!r}, independent recomputation is {want:.2f}")
    return problems
