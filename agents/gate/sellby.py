"""Online sell-by date under the tenant's versioned rule.

FSSAI advisory to e-commerce food business operators (Dec 2024): delivered food must have
"30 percent or 45 days before expiry at the time of delivery". The wording is ambiguous; the
default tenant rule takes the stricter reading (the later of the two cut-offs before expiry).
"""
from __future__ import annotations

from datetime import date, timedelta

from .config import SellbyRule


def online_sellby_date(expiry: date, shelf_life_days: int, rule: SellbyRule, is_food: bool = True) -> date:
    """Last date on which a unit may be sold for online delivery. Non-food: the expiry itself."""
    if not is_food:
        return expiry
    by_fraction = timedelta(days=int(round(rule.min_fraction_remaining * shelf_life_days)))
    by_days = timedelta(days=rule.min_days_remaining)
    if rule.combine == "max":
        cutoff = max(by_fraction, by_days)
    elif rule.combine == "min":
        cutoff = min(by_fraction, by_days)
    else:
        raise ValueError(f"unknown combine mode {rule.combine!r}")
    return expiry - cutoff
