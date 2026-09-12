"""Pydantic v2 models mirroring docs/schemas/play.schema.json and gap.schema.json.

The JSON Schema is the single source of truth (DECISIONS §2.4); these models mirror it
field-for-field and tests/contract/test_schema_sync.py fails on drift in either direction.
"""
from __future__ import annotations

import warnings
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

# The Play schema names a field `copy` (DECISIONS §2.4); pydantic warns that it shadows BaseModel.copy.
warnings.filterwarnings("ignore", message='Field name "copy" in "Play" shadows an attribute')

Objective = Literal[
    "clear_online_sellby", "clear_expiry", "prevent_stockout", "rebalance", "revive_slow_mover"
]
DeadlineType = Literal["online_sellby", "expiry", "lead_time"]
Mechanic = Literal[
    "bundle", "usual_order_addon", "substitution", "preorder", "subscription_nudge",
    "coupon", "outlet_markdown", "transfer_plus_nudge",
]
Channel = Literal["web_chat", "app_push", "outlet"]
CopyStatus = Literal["pending", "generated", "validated", "rejected"]
GuardrailRule = Literal[
    "margin_floor", "frequency_cap", "consent_required", "sellby_disclosure",
    "subscription_protect", "no_cannibalise_stockout", "holdout_required", "cite_or_drop",
]
CitationType = Literal["gap", "estimator", "outcome", "policy", "forecast", "stock"]
PlayStatus = Literal[
    "proposed", "approved", "modified", "rejected", "running", "measured", "unmeasured"
]
GapType = Literal[
    "online_sellby_breach", "expiry_writeoff", "stockout_risk", "rebalance", "slow_mover"
]

MECHANICS: tuple[str, ...] = (
    "bundle", "usual_order_addon", "substitution", "preorder", "subscription_nudge",
    "coupon", "outlet_markdown", "transfer_plus_nudge",
)
GUARDRAIL_RULES: tuple[str, ...] = (
    "margin_floor", "frequency_cap", "consent_required", "sellby_disclosure",
    "subscription_protect", "no_cannibalise_stockout", "holdout_required", "cite_or_drop",
)


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class Target(_Strict):
    sku: str
    node_ids: list[str] = Field(min_length=1)
    batch_ids: list[str]
    units: int = Field(ge=1)
    deadline_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    deadline_type: DeadlineType


class MechanicParams(_Strict):
    discount_pct: float | None = Field(default=None, ge=0, le=100)
    bundle_sku: str | None = None
    bundle_price: float | None = Field(default=None, ge=0)
    transfer_to_node: str | None = None
    transfer_units: int | None = Field(default=None, ge=0)
    preorder_eta_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    markdown_pct: float | None = Field(default=None, ge=0, le=100)


class AudienceFilters(_Strict):
    min_affinity: float | None = Field(default=None, ge=0, le=1)
    recency_days: int | None = Field(default=None, ge=1)
    node_radius_km: float | None = Field(default=None, ge=0)


class Audience(_Strict):
    segment_ids: list[str] = Field(min_length=1)
    filters: AudienceFilters
    purpose: Literal["marketing"]
    size_before_consent: int = Field(ge=0)
    size_after_consent: int = Field(ge=0)


class Window(_Strict):
    start: str
    end: str


LangCode = Annotated[str, StringConstraints(pattern=r"^[a-z]{2}$")]


class CopyVariant(_Strict):
    segment_id: str
    language: str = Field(pattern=r"^[a-z]{2}$")
    text: str = Field(min_length=1, max_length=600)
    disclosure_included: bool


class Copy(_Strict):
    language_set: list[LangCode] = Field(min_length=1)
    variants: list[CopyVariant]
    copy_status: CopyStatus


class ExpectedOutcome(_Strict):
    units: float = Field(ge=0)
    margin_inr: float
    waste_avoided_inr: float = Field(ge=0)
    discount_cost_inr: float = Field(ge=0)
    ci_low: float = Field(ge=0)
    ci_high: float = Field(ge=0)
    prior_n: float = Field(ge=0)
    measured_n: int = Field(ge=0)
    estimator_version: str


class Counterfactuals(_Strict):
    do_nothing_inr: float = Field(ge=0)
    blanket_markdown_inr: float = Field(ge=0)
    blanket_markdown_pct: float = Field(ge=0, le=100)


class Holdout(_Strict):
    fraction: float = Field(ge=0.05, le=0.9)
    seed: str = Field(min_length=4)
    min_treated_n: int = Field(ge=1)


class GuardrailResult(_Strict):
    rule: GuardrailRule
    passed: bool
    detail: str


class Citation(_Strict):
    type: CitationType
    ref: str = Field(min_length=1)


class Alternative(_Strict):
    mechanic: str
    mechanic_params: dict[str, Any]
    expected_units: float = Field(ge=0)
    expected_margin_inr: float
    rejected_because: str


class Edit(_Strict):
    field: str
    from_: Any = Field(default=None, alias="from")
    to: Any = None
    at: str


class Cost(_Strict):
    plan_cost_inr: float | None = Field(default=None, ge=0)
    conversation_budget_inr: float | None = Field(default=None, ge=0)
    pct_of_rupees_at_stake: float | None = Field(default=None, ge=0)


class Play(_Strict):
    play_id: str = Field(pattern=r"^play_[A-Za-z0-9_-]{4,}$")
    gap_id: str = Field(pattern=r"^gap_[A-Za-z0-9_-]{4,}$")
    tenant_id: str | None = None
    created_at: str
    objective: Objective
    target: Target
    mechanic: Mechanic
    mechanic_params: MechanicParams
    audience: Audience
    channel: Channel
    window: Window
    copy: Copy
    expected_outcome: ExpectedOutcome
    counterfactuals: Counterfactuals
    holdout: Holdout
    guardrails: list[GuardrailResult]
    rationale: str = Field(min_length=1, max_length=2000)
    citations: list[Citation]
    alternatives: list[Alternative] = Field(max_length=3)
    policy_version: str
    trace_ref: str
    status: PlayStatus
    approved_by: str | None = None
    approved_at: str | None = None
    edits: list[Edit] | None = None
    cost: Cost | None = None


class GapEvidence(_Strict):
    on_hand: int
    projected_sellthrough: float
    forecast_run_id: str
    sellby_rule: str
    inbound: int | None = None
    unit_cost: float | None = None
    margin_per_unit: float | None = None


class Gap(_Strict):
    gap_id: str
    run_id: str | None = None
    type: GapType
    sku: str
    node_id: str
    batch_id: str | None = None
    units_at_risk: int
    deadline_date: str
    deadline_type: DeadlineType
    rupees_at_stake: float
    evidence: GapEvidence


def play_json_schema() -> dict[str, Any]:
    """JSON schema generated from the Pydantic model (by alias, so `edits[].from` matches)."""
    return Play.model_json_schema(by_alias=True)


def gap_json_schema() -> dict[str, Any]:
    return Gap.model_json_schema(by_alias=True)
