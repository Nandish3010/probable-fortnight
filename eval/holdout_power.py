"""Power analysis of the demo holdout design. SIMULATION of the measurement design, not a result.

    python3 eval/holdout_power.py                                   # prints the JSON
    python3 eval/holdout_power.py --out eval/raw/holdout_power_2026-10-14.json

Standard library only. The design is the seeded Tea play: 355 treated, 39 held out (a 90/10 split of
the 394 consented customers; `eval/raw/tea_recorded_beat_2026-10-12.json`, `approve.assignment`).
The test is a two-sided, two-proportion z-test at 95% confidence (alpha = 0.05) and 80% power.

Formula (pooled variance under the null, unpooled under the alternative, unequal allocation):
    q_t, q_c        = share of orders treated / held out (0.9 / 0.1)
    p_c             = base (held-out) conversion; p_t = p_c + delta
    p_bar           = q_t * p_t + q_c * p_c
    N(delta)        = ( z_{1-alpha/2} * sqrt(p_bar (1 - p_bar) (1/q_t + 1/q_c))
                        + z_{power} * sqrt(p_t (1 - p_t) / q_t + p_c (1 - p_c) / q_c) )^2 / delta^2
    power(delta, n_t, n_c) = Phi((delta - z*se0)/se1) + Phi((-delta - z*se0)/se1), z = z_{1-alpha/2},
        se0 = sqrt(p_bar (1 - p_bar) (1/n_t + 1/n_c)), se1 = sqrt(p_t (1-p_t)/n_t + p_c (1-p_c)/n_c)
    minimum detectable lift = the smallest delta with power(delta, 355, 39) = 0.80 (bisection)

Base conversion (the held-out arm's rate). Primary: the seeded tenant's organic 7-day rate for
Darjeeling Tea 100G at DS-04, 2 buyers / 401 customers homed there (0.499%), computed by
`harness.prior_update_demo.organic_rate` on the tenant from `make generate` (seed 20260912), window
5 Sep 03:30Z to 12 Sep 03:30Z. Sensitivity: the chips organic rate 8/401 = 1.995%
(`eval/raw/prior_update_2026-09-28.json`, `rates_used.holdout`) and the estimator's seeded prior mean
Beta(1, 19) = 5% (`agents/gate/estimator.py`, DEFAULT_ALPHA / DEFAULT_BETA).
"""
from __future__ import annotations

import argparse
import json
import math
from statistics import NormalDist

LABEL = "SIMULATION of the measurement design, not a result"
ALPHA = 0.05
POWER = 0.80
N_TREATED = 355
N_HELD_OUT = 39
Q_TREATED = 0.9
Q_HELD_OUT = 0.1
LIFTS_PP = (2.0, 5.0, 10.0)

BASES: dict[str, dict[str, object]] = {
    "tea_organic": {
        "rate": 2 / 401,
        "basis": "seeded tenant, organic 7-day rate for SKU-DARJEELING-TEA-100G at DS-04: 2 buyers / 401 customers homed there (harness.prior_update_demo.organic_rate, seed 20260912, window 2026-09-05T03:30Z to 2026-09-12T03:30Z)",
        "primary": True,
    },
    "chips_organic": {
        "rate": 8 / 401,
        "basis": "eval/raw/prior_update_2026-09-28.json rates_used.holdout: 8 buyers / 401 customers at DS-07, SKU-MASALA-CHIPS-200G",
        "primary": False,
    },
    "seeded_prior_mean": {
        "rate": 1 / 20,
        "basis": "agents/gate/estimator.py DEFAULT_ALPHA / (DEFAULT_ALPHA + DEFAULT_BETA) = 1 / (1 + 19)",
        "primary": False,
    },
}

_N = NormalDist()


def z_two_sided(alpha: float = ALPHA) -> float:
    return _N.inv_cdf(1 - alpha / 2)


def power(delta: float, n_t: float, n_c: float, p_c: float, alpha: float = ALPHA) -> float:
    """Power of the two-sided two-proportion z-test to detect an absolute lift `delta` (a fraction)."""
    p_t = p_c + delta
    n = n_t + n_c
    p_bar = (n_t * p_t + n_c * p_c) / n
    se0 = math.sqrt(p_bar * (1 - p_bar) * (1 / n_t + 1 / n_c))
    se1 = math.sqrt(p_t * (1 - p_t) / n_t + p_c * (1 - p_c) / n_c)
    z = z_two_sided(alpha)
    return _N.cdf((delta - z * se0) / se1) + _N.cdf((-delta - z * se0) / se1)


def min_detectable_lift(n_t: int, n_c: int, p_c: float, target: float = POWER, alpha: float = ALPHA) -> float:
    """Smallest absolute lift (fraction) detected with probability `target`; bisection on `power`."""
    lo, hi = 0.0, 1.0 - p_c - 1e-9
    for _ in range(200):
        mid = (lo + hi) / 2
        if power(mid, n_t, n_c, p_c, alpha) < target:
            lo = mid
        else:
            hi = mid
    return hi


def total_n(delta: float, p_c: float, q_t: float = Q_TREATED, q_c: float = Q_HELD_OUT,
            target: float = POWER, alpha: float = ALPHA) -> int:
    """Total orders (all arms) needed at allocation q_t / q_c to detect lift `delta` (a fraction)."""
    p_t = p_c + delta
    p_bar = q_t * p_t + q_c * p_c
    a = z_two_sided(alpha) * math.sqrt(p_bar * (1 - p_bar) * (1 / q_t + 1 / q_c))
    b = _N.inv_cdf(target) * math.sqrt(p_t * (1 - p_t) / q_t + p_c * (1 - p_c) / q_c)
    return math.ceil(((a + b) / delta) ** 2)


def build() -> dict[str, object]:
    results: dict[str, object] = {}
    for name, base in BASES.items():
        p_c = float(base["rate"])  # type: ignore[arg-type]
        mdl = min_detectable_lift(N_TREATED, N_HELD_OUT, p_c)
        needed = {}
        for pp in LIFTS_PP:
            n = total_n(pp / 100, p_c)
            needed[f"{pp:g}pp"] = {"total_n": n, "treated": round(n * Q_TREATED), "held_out": n - round(n * Q_TREATED)}
        results[name] = {
            "base_conversion": round(p_c, 6),
            "base_basis": base["basis"],
            "primary": base["primary"],
            "min_detectable_lift_pp_at_355_39": round(mdl * 100, 2),
            "total_n_for_lift_at_90_10_split": needed,
        }
    return {
        "label": LABEL,
        "inputs": {
            "design": {"treated": N_TREATED, "held_out": N_HELD_OUT, "split": "90/10", "source": "eval/raw/tea_recorded_beat_2026-10-12.json approve.assignment"},
            "test": "two-sided two-proportion z-test",
            "confidence": 1 - ALPHA,
            "power": POWER,
            "lifts_pp": list(LIFTS_PP),
            "lift_definition": "absolute difference in conversion, percentage points (jobs/measure/run.py)",
        },
        "formula": {
            "total_n": "N = ((z_{1-a/2}*sqrt(pbar*(1-pbar)*(1/qt+1/qc)) + z_power*sqrt(pt*(1-pt)/qt + pc*(1-pc)/qc)) / delta)^2, rounded up; pt = pc + delta; pbar = qt*pt + qc*pc",
            "min_detectable_lift": "smallest delta with Phi((delta - z_{1-a/2}*se0)/se1) = 0.80 at n_t = 355, n_c = 39 (bisection)",
            "z_{1-a/2}": round(z_two_sided(), 6),
            "z_power": round(_N.inv_cdf(POWER), 6),
        },
        "outputs": results,
        "caveats": [
            "Normal approximation. With a base conversion near 0.5% the held-out arm (39 customers) expects about 0.2 responders, so the approximation is rough and an exact test would be less powerful still.",
            "Assumes independent customers, one decision each, a fixed 90/10 split and a known base rate; the real base rate is unmeasured on real customers.",
        ],
        "note": f"{LABEL}. The demo holdout (355 / 39 synthetic orders) is under-powered by design. No lift was measured; the committed Tea result is 1 of 355 vs 0 of 39, inconclusive.",
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", help="write the JSON here instead of printing it")
    args = ap.parse_args()
    text = json.dumps(build(), indent=2, ensure_ascii=False) + "\n"
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text)
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
