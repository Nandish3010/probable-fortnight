"""eval/holdout_power.py against hand-computed values. SIMULATION of the measurement design, not a result."""
from __future__ import annotations

import importlib.util
import json
import math
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("holdout_power", ROOT / "eval" / "holdout_power.py")
hp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(hp)

Z_A = 1.959964  # two-sided 95%
Z_B = 0.841621  # 80% power


def test_z_values():
    assert hp.z_two_sided() == pytest.approx(Z_A, abs=1e-6)
    assert hp.NormalDist().inv_cdf(hp.POWER) == pytest.approx(Z_B, abs=1e-6)


def test_total_n_hand_computed_equal_allocation():
    # p_c = 0.10, delta = 0.05, 50/50: pbar = 0.125
    #   term1 = 1.959964 * sqrt(0.125 * 0.875 * 4)               = 1.29638
    #   term2 = 0.841621 * sqrt(0.15 * 0.85 * 2 + 0.1 * 0.9 * 2) = 0.55509
    #   N = ((1.29638 + 0.55509) / 0.05)^2 = 1371.2 -> 1372 (686 per arm)
    assert hp.total_n(0.05, 0.10, q_t=0.5, q_c=0.5) == 1372


def test_total_n_hand_computed_tea_5pp_90_10():
    # p_c = 2/401 = 0.0049875, delta = 0.05, 90/10: pbar = 0.0499876
    #   term1 = 1.959964 * sqrt(0.0499876 * 0.9500124 * (1/0.9 + 1/0.1)) = 1.42372
    #   term2 = 0.841621 * sqrt(0.0549875 * 0.9450125 / 0.9 + 0.0049875 * 0.9950125 / 0.1) = 0.27577
    #   N = ((1.42372 + 0.27577) / 0.05)^2 = 1155.3 -> 1156
    assert hp.total_n(0.05, 2 / 401) == 1156


def test_total_n_other_lifts_and_bases():
    assert hp.total_n(0.02, 2 / 401) == 3674
    assert hp.total_n(0.10, 2 / 401) == 505
    assert hp.total_n(0.05, 1 / 20) == 2609


def test_mdl_matches_independent_fixed_point():
    # delta = z_a * se0(delta) + z_b * se1(delta), solved by fixed-point iteration
    p_c, n_t, n_c = 2 / 401, 355, 39
    d = 0.1
    for _ in range(500):
        p_t = p_c + d
        p_bar = (n_t * p_t + n_c * p_c) / (n_t + n_c)
        se0 = math.sqrt(p_bar * (1 - p_bar) * (1 / n_t + 1 / n_c))
        se1 = math.sqrt(p_t * (1 - p_t) / n_t + p_c * (1 - p_c) / n_c)
        d = Z_A * se0 + Z_B * se1
    mdl = hp.min_detectable_lift(n_t, n_c, p_c)
    assert mdl == pytest.approx(d, abs=2e-4)
    assert round(mdl * 100, 2) == 12.38
    assert hp.power(mdl, n_t, n_c, p_c) == pytest.approx(0.80, abs=1e-6)


def test_design_cannot_see_5pp():
    for base in (2 / 401, 8 / 401, 0.05):
        assert hp.min_detectable_lift(355, 39, base) > 0.10  # worse than 10 pp on every base


def test_n_at_the_mdl_is_the_design_size():
    p_c = 2 / 401
    mdl = hp.min_detectable_lift(355, 39, p_c)
    # same allocation as the real design (355 / 394), so the two formulas must agree on N = 394
    assert abs(hp.total_n(mdl, p_c, q_t=355 / 394, q_c=39 / 394) - 394) <= 1


def test_committed_output_matches_script():
    committed = json.loads((ROOT / "eval" / "raw" / "holdout_power_2026-10-14.json").read_text())
    assert committed == json.loads(json.dumps(hp.build()))
    assert "SIMULATION" in committed["label"]
    assert "SIMULATION" in committed["note"]
    tea = committed["outputs"]["tea_organic"]
    assert tea["min_detectable_lift_pp_at_355_39"] == 12.38
    assert {k: v["total_n"] for k, v in tea["total_n_for_lift_at_90_10_split"].items()} == {"2pp": 3674, "5pp": 1156, "10pp": 505}


def test_primary_base_rate_matches_seeded_tenant(data_dir):
    from agents.gate.store import LocalStore
    from harness.prior_update_demo import organic_rate

    r = organic_rate(LocalStore(data_dir), "SKU-DARJEELING-TEA-100G", "DS-04", "2026-09-12T03:30:00Z")
    assert (r["buyers"], r["customers_at_node"]) == (2, 401)
    assert hp.BASES["tea_organic"]["rate"] == pytest.approx(r["rate"])
