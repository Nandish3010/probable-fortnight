"""Deterministic estimator (DECISIONS §3.4). Owns every expected number on a play.

Response rate per (mechanic, category, segment) ~ Beta(alpha, beta). Priors are weak by
construction (default alpha=1, beta=19, i.e. 5% with a pseudo-count of 20) and are overwritten
by measurement through `update_prior`. No LLM and no scipy: the Beta quantiles come from a
numeric inverse of the regularized incomplete beta function implemented below.

Formulas (money in INR, `units` = expected target units sold to the audience):
  rate               = alpha / (alpha + beta)
  units              = size_after_consent * rate * avg_qty_per_responder
  waste_avoided_inr  = min(units, units_at_risk) * unit_cost
  coupon             : discount = list_price * discount_pct/100
                       margin = units * (list_price - discount - unit_cost)
  outlet_markdown    : same with markdown_pct
  bundle             : margin = units * (bundle_price - unit_cost - partner_unit_cost)
                       discount_cost = units * max(0, list_price + partner_list_price - bundle_price)
  transfer_plus_nudge: margin = waste_avoided_inr - transfer_cost_per_unit * transfer_units
                       (transfer_units defaults to units_at_risk; units capped at transfer_units)
  other mechanics    : margin = units * (list_price - unit_cost), discount_cost = 0
  ci_low / ci_high   = units at the 5% / 95% Beta quantiles of the rate
  do_nothing_inr     = units_at_risk * unit_cost
  blanket_markdown_inr = baseline_forecast_units * markdown_pct/100 * list_price
                         + max(0, units_at_risk - baseline_forecast_units * markdown_pct/100
                                  * markdown_elasticity) * unit_cost
When several segments are targeted the prior parameters are averaged (mean alpha, mean beta).
"""
from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

ESTIMATOR_VERSION = "est-v1"
DEFAULT_ALPHA = 1.0
DEFAULT_BETA = 19.0
DEFAULT_TRANSFER_COST_PER_UNIT = 2.0
DEFAULT_BLANKET_MARKDOWN_PCT = 20.0
CI_LOW_Q = 0.05
CI_HIGH_Q = 0.95

PriorKey = tuple[str, str, str]
Prior = tuple[float, float, int]
PriorLookup = Callable[[PriorKey], Prior | None] | Mapping[PriorKey, Prior]

DISCOUNT_MECHANICS = frozenset({"coupon", "outlet_markdown", "bundle"})


@dataclass(frozen=True)
class Product:
    sku: str
    category: str
    unit_cost: float
    list_price: float
    margin_floor_pct: float


@dataclass(frozen=True)
class GapFacts:
    units_at_risk: int
    rupees_at_stake: float
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass
class EstimatorContext:
    product: Product
    gap: GapFacts
    audience_size_after_consent: int
    avg_qty_per_responder: float = 1.0
    priors: PriorLookup | None = None
    default_alpha: float = DEFAULT_ALPHA
    default_beta: float = DEFAULT_BETA
    estimator_version: str = ESTIMATOR_VERSION
    transfer_cost_per_unit: float = DEFAULT_TRANSFER_COST_PER_UNIT
    blanket_markdown_pct: float = DEFAULT_BLANKET_MARKDOWN_PCT
    baseline_forecast_units: float | None = None
    markdown_elasticity: float = 1.0
    bundle_partner_unit_cost: float = 0.0
    bundle_partner_list_price: float = 0.0

    def lookup_prior(self, key: PriorKey) -> Prior:
        found: Prior | None = None
        if self.priors is not None:
            found = self.priors(key) if callable(self.priors) else self.priors.get(key)
        if found is None:
            return (self.default_alpha, self.default_beta, 0)
        alpha, beta, n = found
        return (float(alpha), float(beta), int(n))


# ---------------------------------------------------------------------------------------------
# Regularized incomplete beta and its inverse (Numerical Recipes continued fraction).
# ---------------------------------------------------------------------------------------------

def _betacf(a: float, b: float, x: float) -> float:
    max_iter, eps, fpmin = 300, 3e-14, 1e-300
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    d = 1.0 / (d if abs(d) > fpmin else fpmin)
    h = d
    for m in range(1, max_iter + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > fpmin else fpmin)
        c = 1.0 + aa / c
        c = c if abs(c) > fpmin else fpmin
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > fpmin else fpmin)
        c = 1.0 + aa / c
        c = c if abs(c) > fpmin else fpmin
        de = d * c
        h *= de
        if abs(de - 1.0) < eps:
            break
    return h


def beta_cdf(x: float, a: float, b: float) -> float:
    """Regularized incomplete beta I_x(a, b) = P(Beta(a, b) <= x)."""
    if a <= 0 or b <= 0:
        raise ValueError("alpha and beta must be positive")
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    ln_bt = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log1p(-x)
    bt = math.exp(ln_bt)
    if x < (a + 1.0) / (a + b + 2.0):
        return bt * _betacf(a, b, x) / a
    return 1.0 - bt * _betacf(b, a, 1.0 - x) / b


def beta_quantile(q: float, a: float, b: float, tol: float = 1e-12) -> float:
    """Inverse of `beta_cdf` by bisection; exact enough for reporting (abs error < 1e-10)."""
    if not 0.0 <= q <= 1.0:
        raise ValueError("q must lie in [0, 1]")
    if q == 0.0:
        return 0.0
    if q == 1.0:
        return 1.0
    lo, hi = 0.0, 1.0
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if beta_cdf(mid, a, b) < q:
            lo = mid
        else:
            hi = mid
        if hi - lo < tol:
            break
    return 0.5 * (lo + hi)


# ---------------------------------------------------------------------------------------------
# Priors
# ---------------------------------------------------------------------------------------------

def expected_rate(alpha: float, beta: float) -> float:
    return alpha / (alpha + beta)


def update_prior(alpha: float, beta: float, responders: int, non_responders: int) -> tuple[float, float]:
    """Beta-Binomial conjugate update with exact counts (DECISIONS §5.7)."""
    if responders < 0 or non_responders < 0:
        raise ValueError("counts must be non-negative")
    return (alpha + responders, beta + non_responders)


def _prior_for_draft(play_draft: dict[str, Any], ctx: EstimatorContext) -> tuple[float, float, int]:
    mechanic = play_draft["mechanic"]
    segment_ids = list(play_draft.get("audience", {}).get("segment_ids") or ["*"])
    priors = [ctx.lookup_prior((mechanic, ctx.product.category, s)) for s in segment_ids]
    alpha = sum(p[0] for p in priors) / len(priors)
    beta = sum(p[1] for p in priors) / len(priors)
    n_measured = int(round(sum(p[2] for p in priors) / len(priors)))
    return alpha, beta, n_measured


# ---------------------------------------------------------------------------------------------
# Estimate
# ---------------------------------------------------------------------------------------------

def _r2(x: float) -> float:
    return round(float(x), 2)


def _discount_per_unit(mechanic: str, params: Mapping[str, Any], ctx: EstimatorContext) -> float:
    price = ctx.product.list_price
    if mechanic == "coupon":
        return price * float(params.get("discount_pct") or 0.0) / 100.0
    if mechanic == "outlet_markdown":
        return price * float(params.get("markdown_pct") or 0.0) / 100.0
    if mechanic == "bundle":
        bundle_price = float(params.get("bundle_price") or 0.0)
        return max(0.0, price + ctx.bundle_partner_list_price - bundle_price)
    return 0.0


def unit_economics(mechanic: str, params: Mapping[str, Any], ctx: EstimatorContext) -> dict[str, float]:
    """Per-unit net price, cost and margin for a mechanic; shared with the margin_floor guardrail."""
    p = ctx.product
    if mechanic == "bundle":
        net_price = float(params.get("bundle_price") or 0.0)
        cost = p.unit_cost + ctx.bundle_partner_unit_cost
    else:
        net_price = p.list_price - _discount_per_unit(mechanic, params, ctx)
        cost = p.unit_cost
    margin = net_price - cost
    margin_pct = (margin / net_price * 100.0) if net_price > 0 else (0.0 if margin >= 0 else -100.0)
    return {"net_price": net_price, "unit_cost": cost, "margin": margin, "margin_pct": margin_pct}


def estimate(play_draft: dict[str, Any], ctx: EstimatorContext) -> dict[str, Any]:
    mechanic = play_draft["mechanic"]
    params: Mapping[str, Any] = play_draft.get("mechanic_params") or {}
    alpha, beta, n_measured = _prior_for_draft(play_draft, ctx)
    rate = expected_rate(alpha, beta)
    audience = int(ctx.audience_size_after_consent)
    scale = audience * ctx.avg_qty_per_responder
    units = scale * rate
    ci_low = scale * beta_quantile(CI_LOW_Q, alpha, beta)
    ci_high = scale * beta_quantile(CI_HIGH_Q, alpha, beta)

    units_at_risk = ctx.gap.units_at_risk
    unit_cost = ctx.product.unit_cost
    discount = _discount_per_unit(mechanic, params, ctx)

    if mechanic == "transfer_plus_nudge":
        transfer_units = int(params.get("transfer_units") or units_at_risk)
        units = min(units, float(transfer_units))
        ci_low = min(ci_low, float(transfer_units))
        ci_high = min(ci_high, float(transfer_units))
        waste_avoided = min(units, units_at_risk) * unit_cost
        margin = waste_avoided - ctx.transfer_cost_per_unit * transfer_units
        discount_cost = 0.0
    else:
        waste_avoided = min(units, units_at_risk) * unit_cost
        econ = unit_economics(mechanic, params, ctx)
        margin = units * econ["margin"]
        discount_cost = units * discount

    expected_outcome = {
        "units": _r2(units),
        "margin_inr": _r2(margin),
        "waste_avoided_inr": _r2(waste_avoided),
        "discount_cost_inr": _r2(discount_cost),
        "ci_low": _r2(ci_low),
        "ci_high": _r2(ci_high),
        "prior_n": _r2(alpha + beta),
        "measured_n": int(n_measured),
        "estimator_version": ctx.estimator_version,
    }
    return {"expected_outcome": expected_outcome, "counterfactuals": counterfactuals(play_draft, ctx)}


def counterfactuals(play_draft: dict[str, Any], ctx: EstimatorContext) -> dict[str, float]:
    """do_nothing = write-off of everything at risk; blanket markdown = margin given away on the
    baseline volume plus whatever is still written off after the markdown's uplift."""
    p = ctx.product
    units_at_risk = float(ctx.gap.units_at_risk)
    params: Mapping[str, Any] = play_draft.get("mechanic_params") or {}
    markdown_pct = float(params.get("markdown_pct") or ctx.blanket_markdown_pct)
    baseline = ctx.baseline_forecast_units
    if baseline is None:
        baseline = float(ctx.gap.evidence.get("projected_sellthrough") or 0.0)
    frac = markdown_pct / 100.0
    discount_given = baseline * frac * p.list_price
    uplift_units = baseline * frac * ctx.markdown_elasticity
    remaining_writeoff = max(0.0, units_at_risk - uplift_units) * p.unit_cost
    return {
        "do_nothing_inr": _r2(units_at_risk * p.unit_cost),
        "blanket_markdown_inr": _r2(discount_given + remaining_writeoff),
        "blanket_markdown_pct": _r2(markdown_pct),
    }
