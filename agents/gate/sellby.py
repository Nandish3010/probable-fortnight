"""Online sell-by date under the tenant's versioned rule.

FSSAI's advisory to e-commerce food business operators, 3 Dec 2024 (file no.
RCD-13/1/2024-Regulatory-FSSAI(E-13150), paragraph 4), as quoted in the README, reads: delivered
food should have "30 percent or 45 days before expiry at the time of delivery". Primary:
https://fssai.gov.in/upload/advisories/2024/12/674efa161d756Adobe%20Scan%203%20Dec%202024.pdf
The wording is ambiguous, so `SellbyRule.combine` picks which of the two
cut-offs (30% of shelf life, or 45 days) actually applies:

- `combine = "max"` is the STRICTER reading: whichever cut-off subtracts MORE time from expiry
  wins, so the online sell-by date lands EARLIER -- less time to sell online.
- `combine = "min"` is the MORE LENIENT reading: whichever cut-off subtracts LESS time from
  expiry wins, so the online sell-by date lands LATER -- more time to sell online.

`config/tenant.demo.toml` sets `combine = "min"` (the lenient reading) -- this is a policy
parameter each retailer sets for itself, not a fixed legal interpretation; there is no single
"default" reading baked into this module.
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
