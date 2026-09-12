from datetime import date

import pytest

from agents.gate.config import SellbyRule, load_tenant
from agents.gate.sellby import online_sellby_date

STRICT = SellbyRule("v1-strict", 0.30, 45, "max")


def test_strict_rule_takes_the_later_cutoff():
    # 60-day shelf life: 30% = 18 days < 45 days -> 45 days before expiry
    assert online_sellby_date(date(2026, 10, 2), 60, STRICT) == date(2026, 8, 18)
    # 365-day shelf life: 30% = 110 days > 45 -> 110 days before expiry
    assert online_sellby_date(date(2027, 1, 24), 365, STRICT) == date(2026, 10, 6)


def test_lenient_rule_takes_the_earlier_cutoff():
    lenient = SellbyRule("v1-lenient", 0.30, 45, "min")
    assert online_sellby_date(date(2026, 10, 2), 60, lenient) == date(2026, 9, 14)


def test_non_food_is_sellable_until_expiry():
    assert online_sellby_date(date(2026, 10, 2), 60, STRICT, is_food=False) == date(2026, 10, 2)


def test_tenant_rule_is_versioned_and_permits_perishables():
    t = load_tenant()
    assert t.sellby_rule.version == "v1-either"
    assert t.sellby_rule.combine == "min"
    # a 7-day bread is still sellable online two days before expiry
    assert online_sellby_date(date(2026, 9, 19), 7, t.sellby_rule) == date(2026, 9, 17)


def test_unknown_combine_rejected():
    with pytest.raises(ValueError):
        online_sellby_date(date(2026, 10, 2), 60, SellbyRule("x", 0.3, 45, "avg"))
