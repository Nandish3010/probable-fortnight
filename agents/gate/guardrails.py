"""The eight guardrails (DECISIONS §2.5). Deterministic Python; no LLM touches money or the
right to act. `check` always returns one result per rule so the Planner sees every failure at
once and the Play card can list all eight.
"""
from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Iterator, Mapping
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


# ---------------------------------------------------------------------------------------------
# cite_or_drop: which figures a rationale claims, and which figures the play can vouch for
# ---------------------------------------------------------------------------------------------

# Spans that are never a claim, however many digits they hold.
_ISO_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}(?:T[\d:.]+Z?)?\b")
_NUMERIC_DATE = re.compile(r"\b(?:\d{1,2}[/.-]\d{1,2}[/.-]\d{4}|\d{4}/\d{1,2}/\d{1,2})\b")
_MONTH = (
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|Aug(?:ust)?"
    r"|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
)
_TEXT_DATE = re.compile(
    rf"\b(?:\d{{1,2}}(?:st|nd|rd|th)?\s+(?:of\s+)?{_MONTH}\b\.?(?:,?\s+\d{{4}}\b)?"  # 18 Sept 2026
    rf"|{_MONTH}\b\.?\s+\d{{1,2}}(?:st|nd|rd|th)?\b(?:,?\s+\d{{4}}\b)?"  # Sept 18, 2026
    rf"|{_MONTH}\b\.?,?\s+\d{{4}}\b)"  # September 2026
)
_ID_LIKE = re.compile(r"\b[A-Za-z][A-Za-z0-9]*[-_][A-Za-z0-9_-]*\d[A-Za-z0-9_-]*\b")  # DS-07, run_04 (one leading letter: linear)
_NOT_CLAIMS = (_ISO_DATE, _NUMERIC_DATE, _TEXT_DATE, _ID_LIKE)

# One numeric token, taken whole: digits (commas allowed; grouping is validated by _split_groups),
# an optional fraction, or a bare ".5". The guard refuses a token glued to a word (v1, p50, DS07,
# run_04) and the tail of a decimal whose head was refused ("p161.52" yields nothing, never "52");
# a currency word may touch its digits (INR58.50, Rs874). _NUMBER_ANY has no guard: digits inside
# an identifier are still facts the play states.
_NUMBER_BODY = r"{guard}(?P<int>\d+(?:,\d+)*)(?P<frac>\.\d+)?|(?<![\w.])(?P<lead>\.\d+)"
_NUMBER = re.compile(_NUMBER_BODY.format(guard=r"(?:(?<=\bRs)|(?<=\bINR)|(?<!\w))(?<!\d\.)"))
_NUMBER_ANY = re.compile(_NUMBER_BODY.format(guard=""))

# A minus sign is a sign only when it is not a hyphen or a range dash: not glued to a preceding
# word, digit, ")", "]" or "%" ("20-30", "DS-07", "10%-20%"). A currency marker may sit between the
# sign and the digits ("-₹161.52") or before the sign ("₹-161.52", "INR -161.52").
_NEGATIVE_BEFORE = re.compile(
    r"(?:(?:^|[^\w)\]%.])[-−–](?:(?:₹|\bRs\.?|\bINR)\s?)?|(?:₹|\bRs\.?|\bINR)\s?[-−–])$"
)


@dataclass(frozen=True)
class _Number:
    start: int
    end: int
    value: float  # signed
    decimal: bool  # written with a fractional part
    negative: bool  # written with an explicit minus sign


def _split_groups(digits: str) -> list[str]:
    """"1,795,464" (Western) and "17,95,464" (Indian) are one number; "20,30,40" is a list."""
    parts = digits.split(",")
    if len(parts) == 1:
        return parts
    head, *mid, last = parts
    western = len(head) <= 3 and len(last) == 3 and all(len(p) == 3 for p in mid)
    indian = len(head) <= 2 and len(last) == 3 and all(len(p) == 2 for p in mid)
    return ["".join(parts)] if western or indian else parts


def _tokens(text: str, *, glued: bool = False) -> Iterator[_Number]:
    """Every numeric token in `text`, whole and in order. `glued=True` also yields the digits
    inside identifiers (the 07 of DS-07, the 200 of SKU-CHIPS-200G)."""
    for m in (_NUMBER_ANY if glued else _NUMBER).finditer(text):
        negative = _NEGATIVE_BEFORE.search(text, max(0, m.start() - 12), m.start()) is not None
        if m.group("lead"):
            value = float("0" + m.group("lead"))
            yield _Number(m.start(), m.end(), -value if negative else value, True, negative)
            continue
        groups = _split_groups(m.group("int"))
        pos = m.start("int")
        for i, digits in enumerate(groups):
            frac = m.group("frac") if i == len(groups) - 1 else None
            value = float(digits + (frac or ""))
            neg = negative and i == 0
            end = pos + len(digits) + len(frac or "")
            yield _Number(pos, end, -value if neg else value, frac is not None, neg)
            pos = end + 1  # past the comma


def numbers_in_text(text: str) -> list[float]:
    """The figures a reader would take as claims in `text`: signed floats, in order.

    A figure is a whole numeric token, never a piece of one: an optional minus sign, digits with
    Western (1,795,464) or Indian (17,95,464) grouping, an optional fraction (161.52, .5). A
    currency marker (₹, Rs, Rs., INR), a trailing % and unit letters (200G) are not part of the
    value. Rules:
      * a claim is any decimal, any explicit negative, or any integer of 10 or more; a bare
        single-digit integer is a count ("3 segments"), not a claim;
      * "-" is a sign only when not glued to a preceding word, digit, ")" or "%": "20-30" is the
        two figures 20 and 30, and "-161.52" is one negative figure;
      * never claims: ISO dates and timestamps, "18 Sept 2026" and dd/mm/yyyy dates, and
        identifiers (DS-07, SKU-CHIPS-200G, run_04, v1, p50, DS07);
      * magnitude words (k, lakh, crore, M) are not interpreted: "1.2 lakh" claims 1.2, which must
        then match a cited 1.2 as written.
    """
    skip = [m.span() for pattern in _NOT_CLAIMS for m in pattern.finditer(text)]
    return [
        n.value
        for n in _tokens(text)
        if (n.decimal or n.negative or abs(n.value) >= 10)
        and not any(s <= n.start and n.end <= e for s, e in skip)
    ]


def _fmt(value: float) -> str:
    """A figure as the rationale wrote it: 52, 161.52, -161.52, 1795464 (never 1.79546e+06)."""
    return str(int(value)) if value.is_integer() else repr(value)


def _walk_numbers(obj: Any, acc: list[float]) -> None:
    if isinstance(obj, bool):
        return
    if isinstance(obj, int | float):
        acc.append(float(obj))
    elif isinstance(obj, str):
        acc.extend(n.value for n in _tokens(obj, glued=True))
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
    # guardrails is tool-computed (check_guardrails), never LLM-authored: a rationale restating a
    # number from a passed rule's own detail (a margin percent, an audience count) is citing a
    # verified fact, not inventing one, even though that number lives outside expected_outcome.
    # alternatives carries the estimator's figures for the mechanics the play rejected (expected
    # units, expected margin, transfer units): a rationale explaining why one mechanic beat another
    # quotes them, and they are as much the play's own fields as expected_outcome is.
    for key in ("expected_outcome", "counterfactuals", "alternatives", "target", "mechanic_params", "audience", "holdout", "guardrails"):
        _walk_numbers(draft.get(key) or {}, acc)
    # Percent forms of fractions (holdout 0.1 -> 10) and rupee values expressed in whole rupees.
    acc.extend(v * 100.0 for v in list(acc) if 0 < abs(v) < 1)
    return acc


def _matches(value: float, cited: Iterable[float]) -> bool:
    """Whether `value` (a figure from the rationale) is one of `cited`.

    The window is 0.1% of the cited value, never under 0.5: it tolerates real rounding
    differences (₹9,194 for 9194.12, 23 units for 22.98) without accepting a materially different
    number as "the same" one (it was 0.5% once, which opened a +-46 window around ₹9,200).
    Sign: a figure written with an explicit minus must match a negative cited value; an unsigned
    figure matches on magnitude, so "a loss of 161.52" matches a cited -161.52.
    """
    for c in cited:
        reference = c if value < 0 else abs(c)
        if abs(value - reference) <= max(0.5, 0.001 * abs(c)):
            return True
    return False


def rule_cite_or_drop(draft: dict[str, Any], ctx: GuardrailContext) -> dict[str, Any]:
    """Real scope, stated plainly rather than implied by the name: this is not a strict
    per-citation link check (it does not verify *which* citation backs *which* number in the
    rationale). It checks that every number the rationale states also appears somewhere in the
    play's own structured fields (expected_outcome, counterfactuals, alternatives, target,
    mechanic_params, audience, holdout) or in a guardrail rule's own tool-computed detail string
    -- i.e. the model did not invent a number that appears nowhere in the facts it was given.
    That is a real and useful check (see test_cite_or_drop_rejects_an_uncited_number), but a
    rationale can still cite a true number for the wrong reason; this rule cannot catch that.
    Figures that live only in the gap row or a forecast run (a citation carries just the id) are
    not in the play, so they do not count as cited.
    """
    citations = draft.get("citations") or []
    unresolved = []
    if ctx.resolve_citation is not None:
        unresolved = [f"{c.get('type')}:{c.get('ref')}" for c in citations if not ctx.resolve_citation(str(c.get("type")), str(c.get("ref")))]
    cited = cited_numbers(draft)
    claimed = numbers_in_text(str(draft.get("rationale") or ""))
    uncited = sorted({v for v in claimed if not _matches(v, cited)})
    problems = []
    if uncited:
        problems.append("uncited numbers in rationale: " + ", ".join(_fmt(v) for v in uncited))
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
