"""The eight guardrails (DECISIONS §2.5). Deterministic Python; no LLM touches money or the
right to act. `check` always returns one result per rule so the Planner sees every failure at
once and the Play card can list all eight.
"""
from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from .config import TenantConfig, load_tenant
from .estimator import DISCOUNT_MECHANICS, EstimatorContext, GapFacts, Product, unit_economics
from .models import GUARDRAIL_RULES

NEAR_DEADLINE_OBJECTIVES = frozenset({"clear_online_sellby", "clear_expiry"})
NEAR_DEADLINE_TYPES = frozenset({"online_sellby", "expiry"})
CitationResolver = Callable[[str, str], bool]


@dataclass
class GuardrailContext:
    product: Product
    tenant: TenantConfig = field(default_factory=load_tenant)
    audience_customer_ids: list[str] | None = None
    recent_plays_count: Mapping[str, int] = field(default_factory=dict)
    consented_customer_ids: frozenset[str] = frozenset()
    subscribers_for_sku: frozenset[str] = frozenset()
    stockout_gap_skus_at_node: frozenset[str] = frozenset()
    resolve_citation: CitationResolver | None = None
    bundle_partner_unit_cost: float = 0.0
    bundle_partner_list_price: float = 0.0

    def estimator_context(self, units_at_risk: int = 0) -> EstimatorContext:
        return EstimatorContext(
            product=self.product,
            gap=GapFacts(units_at_risk=units_at_risk, rupees_at_stake=0.0),
            audience_size_after_consent=0,
            bundle_partner_unit_cost=self.bundle_partner_unit_cost,
            bundle_partner_list_price=self.bundle_partner_list_price,
        )


def _result(rule: str, passed: bool, detail: str) -> dict[str, Any]:
    return {"rule": rule, "passed": bool(passed), "detail": detail}


# ---------------------------------------------------------------------------------------------
# Audience helpers
# ---------------------------------------------------------------------------------------------

def filter_audience_by_consent(customer_ids: Iterable[str], consented: Iterable[str]) -> list[str]:
    """Keep only customers with marketing consent, preserving order and dropping duplicates."""
    allowed = set(consented)
    out, seen = [], set()
    for cid in customer_ids:
        if cid in allowed and cid not in seen:
            seen.add(cid)
            out.append(cid)
    return out


def filter_audience_by_frequency_cap(customer_ids: Iterable[str], recent_plays_count: Mapping[str, int], cap: int) -> list[str]:
    return [cid for cid in customer_ids if int(recent_plays_count.get(cid, 0)) < cap]


def filter_audience_by_subscription(customer_ids: Iterable[str], subscribers: Iterable[str]) -> list[str]:
    subs = set(subscribers)
    return [cid for cid in customer_ids if cid not in subs]


# ---------------------------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------------------------

def rule_margin_floor(draft: dict[str, Any], ctx: GuardrailContext) -> dict[str, Any]:
    floor = ctx.product.margin_floor_pct
    econ = unit_economics(draft["mechanic"], draft.get("mechanic_params") or {}, ctx.estimator_context())
    pct = econ["margin_pct"]
    detail = (
        f"net margin {pct:.2f}% (net price {econ['net_price']:.2f}, cost {econ['unit_cost']:.2f}) "
        f"vs {ctx.product.category} floor {floor:.2f}%"
    )
    return _result("margin_floor", pct >= floor, detail)


def rule_frequency_cap(draft: dict[str, Any], ctx: GuardrailContext) -> dict[str, Any]:
    cap = int(ctx.tenant.thresholds.get("frequency_cap_per_7d", 2))
    if ctx.audience_customer_ids is None:
        return _result("frequency_cap", True, f"no audience ids supplied; cap {cap}/7d enforced at assignment")
    over = [c for c in ctx.audience_customer_ids if int(ctx.recent_plays_count.get(c, 0)) >= cap]
    if over:
        return _result("frequency_cap", False, f"{len(over)} of {len(ctx.audience_customer_ids)} customers already at {cap} plays in 7 days: {', '.join(sorted(over)[:5])}")
    return _result("frequency_cap", True, f"all {len(ctx.audience_customer_ids)} customers under {cap} plays in 7 days")


def rule_consent_required(draft: dict[str, Any], ctx: GuardrailContext) -> dict[str, Any]:
    aud = draft.get("audience") or {}
    if draft.get("channel") == "outlet":
        return _result("consent_required", True, "outlet channel: no personal message, consent not required")
    if aud.get("purpose") != "marketing":
        return _result("consent_required", False, f"audience purpose {aud.get('purpose')!r} is not 'marketing'")
    before, after = int(aud.get("size_before_consent", 0)), int(aud.get("size_after_consent", 0))
    if after > before:
        return _result("consent_required", False, f"size_after_consent {after} exceeds size_before_consent {before}")
    if ctx.audience_customer_ids is not None:
        missing = [c for c in ctx.audience_customer_ids if c not in ctx.consented_customer_ids]
        if missing:
            return _result("consent_required", False, f"{len(missing)} audience customers lack marketing consent on {draft.get('channel')}: {', '.join(sorted(missing)[:5])}")
    return _result("consent_required", True, f"audience filtered by consent: {before} -> {after}")


def _near_deadline(draft: dict[str, Any]) -> bool:
    target = draft.get("target") or {}
    return draft.get("objective") in NEAR_DEADLINE_OBJECTIVES or target.get("deadline_type") in NEAR_DEADLINE_TYPES


def rule_sellby_disclosure(draft: dict[str, Any], ctx: GuardrailContext) -> dict[str, Any]:
    if not _near_deadline(draft):
        return _result("sellby_disclosure", True, "not a near-deadline play; disclosure not required")
    copy = draft.get("copy") or {}
    variants = copy.get("variants") or []
    if not variants:
        if copy.get("copy_status", "pending") == "pending":
            return _result("sellby_disclosure", True, "copy pending; best-before disclosure enforced at copy validation")
        return _result("sellby_disclosure", False, "near-deadline play has no copy variants to carry the best-before line")
    missing = [f"{v.get('segment_id')}/{v.get('language')}" for v in variants if not v.get("disclosure_included")]
    if missing:
        return _result("sellby_disclosure", False, f"best-before disclosure missing in {len(missing)} variant(s): {', '.join(missing)}")
    return _result("sellby_disclosure", True, f"best-before stated in all {len(variants)} variant(s)")


def rule_subscription_protect(draft: dict[str, Any], ctx: GuardrailContext) -> dict[str, Any]:
    if draft.get("mechanic") not in DISCOUNT_MECHANICS:
        return _result("subscription_protect", True, f"{draft.get('mechanic')} is not a discount play")
    if ctx.audience_customer_ids is None:
        return _result("subscription_protect", True, "no audience ids supplied; subscribers excluded at assignment")
    hit = [c for c in ctx.audience_customer_ids if c in ctx.subscribers_for_sku]
    if hit:
        return _result("subscription_protect", False, f"{len(hit)} active subscriber(s) of {ctx.product.sku} in a discount audience: {', '.join(sorted(hit)[:5])}")
    return _result("subscription_protect", True, f"no active subscribers of {ctx.product.sku} in audience")


STOCKOUT_SAFE_MECHANICS = frozenset({"preorder", "substitution", "transfer_plus_nudge"})


def rule_no_cannibalise_stockout(draft: dict[str, Any], ctx: GuardrailContext) -> dict[str, Any]:
    sku = (draft.get("target") or {}).get("sku")
    nodes = (draft.get("target") or {}).get("node_ids") or []
    if draft.get("objective") == "prevent_stockout" or draft.get("mechanic") in STOCKOUT_SAFE_MECHANICS:
        return _result("no_cannibalise_stockout", True, f"{draft.get('mechanic')} does not push {sku}; stockout rule not applicable")
    if sku in ctx.stockout_gap_skus_at_node:
        return _result("no_cannibalise_stockout", False, f"{sku} has an open stockout gap at {', '.join(nodes)}")
    return _result("no_cannibalise_stockout", True, f"no stockout gap for {sku} at {', '.join(nodes)}")


def rule_holdout_required(draft: dict[str, Any], ctx: GuardrailContext) -> dict[str, Any]:
    h = draft.get("holdout") or {}
    min_fraction = float(ctx.tenant.thresholds.get("min_holdout_fraction", 0.05))
    fraction = h.get("fraction")
    min_treated = h.get("min_treated_n")
    if fraction is None or not isinstance(fraction, int | float) or fraction < min_fraction or fraction > 0.9:
        return _result("holdout_required", False, f"holdout fraction {fraction!r} outside [{min_fraction}, 0.9]")
    if not isinstance(min_treated, int) or isinstance(min_treated, bool) or min_treated < 1:
        return _result("holdout_required", False, f"min_treated_n {min_treated!r} not set to a positive integer")
    if not h.get("seed"):
        return _result("holdout_required", False, "holdout seed missing")
    return _result("holdout_required", True, f"holdout {fraction:.0%}, min_treated_n {min_treated}")


_ISO_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}(?:T[\d:.]+Z?)?\b")
_NUMBER = re.compile(r"(?<![A-Za-z0-9_-])(\d{1,3}(?:,\d{3})+|\d+)(\.\d+)?")
_ID_LIKE = re.compile(r"\b[A-Za-z]+[A-Za-z0-9]*[-_][A-Za-z0-9_-]*\d[A-Za-z0-9_-]*\b")


def numbers_in_text(text: str) -> list[float]:
    """Numbers a reader would take as a claim: any decimal, or any integer >= 10. ISO dates and
    identifiers such as DS-07 or SKU-CHIPS-200G are ignored."""
    cleaned = _ISO_DATE.sub(" ", text)
    cleaned = _ID_LIKE.sub(" ", cleaned)
    out = []
    for whole, frac in _NUMBER.findall(cleaned):
        value = float(whole.replace(",", "") + (frac or ""))
        if frac or value >= 10:
            out.append(value)
    return out


def _walk_numbers(obj: Any, acc: list[float]) -> None:
    if isinstance(obj, bool):
        return
    if isinstance(obj, int | float):
        acc.append(float(obj))
    elif isinstance(obj, str):
        acc.extend(numbers_in_text(obj))
        acc.extend(float(m.group(0)) for m in re.finditer(r"\d+\.\d+|\d+", obj))
    elif isinstance(obj, Mapping):
        for v in obj.values():
            _walk_numbers(v, acc)
    elif isinstance(obj, list | tuple):
        for v in obj:
            _walk_numbers(v, acc)


def cited_numbers(draft: dict[str, Any]) -> list[float]:
    acc: list[float] = []
    for c in draft.get("citations") or []:
        _walk_numbers(c.get("ref", ""), acc)
    for key in ("expected_outcome", "counterfactuals", "target", "mechanic_params", "audience", "holdout"):
        _walk_numbers(draft.get(key) or {}, acc)
    # Percent forms of fractions (holdout 0.1 -> 10) and rupee values expressed in whole rupees.
    acc.extend(v * 100.0 for v in list(acc) if 0 < v < 1)
    return acc


def _matches(value: float, cited: Iterable[float]) -> bool:
    for c in cited:
        if abs(value - c) <= max(0.5, 0.005 * abs(c)):
            return True
    return False


def rule_cite_or_drop(draft: dict[str, Any], ctx: GuardrailContext) -> dict[str, Any]:
    citations = draft.get("citations") or []
    unresolved = []
    if ctx.resolve_citation is not None:
        unresolved = [f"{c.get('type')}:{c.get('ref')}" for c in citations if not ctx.resolve_citation(str(c.get("type")), str(c.get("ref")))]
    cited = cited_numbers(draft)
    claimed = numbers_in_text(str(draft.get("rationale") or ""))
    uncited = sorted({v for v in claimed if not _matches(v, cited)})
    problems = []
    if uncited:
        problems.append("uncited numbers in rationale: " + ", ".join(f"{v:g}" for v in uncited))
    if unresolved:
        problems.append("citations that do not resolve: " + ", ".join(unresolved))
    if problems:
        return _result("cite_or_drop", False, "; ".join(problems))
    return _result("cite_or_drop", True, f"{len(claimed)} number(s) in rationale all cited; {len(citations)} citation(s) resolve")


RULES: dict[str, Callable[[dict[str, Any], GuardrailContext], dict[str, Any]]] = {
    "margin_floor": rule_margin_floor,
    "frequency_cap": rule_frequency_cap,
    "consent_required": rule_consent_required,
    "sellby_disclosure": rule_sellby_disclosure,
    "subscription_protect": rule_subscription_protect,
    "no_cannibalise_stockout": rule_no_cannibalise_stockout,
    "holdout_required": rule_holdout_required,
    "cite_or_drop": rule_cite_or_drop,
}
assert tuple(RULES) == GUARDRAIL_RULES


def check(play_draft: dict[str, Any], ctx: GuardrailContext) -> dict[str, Any]:
    results = [RULES[rule](play_draft, ctx) for rule in GUARDRAIL_RULES]
    return {"results": results, "all_passed": all(r["passed"] for r in results)}
