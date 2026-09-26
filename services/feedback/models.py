"""Pydantic mirror of docs/schemas/feedback_response.schema.json. The schema is the source of
truth: the API validates every submission against it first (services/feedback/validate.py), and
tests/contract/test_feedback_schema.py fails if the field names or enums here drift from it. The
show-if rules (e.g. c1..c4 absent when c0 is "no") live only in the schema's if/then blocks."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Short = Field(default=None, min_length=1, max_length=200)
Long = Field(default=None, min_length=1, max_length=1000)


class FeedbackContact(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=120)
    reach: str | None = Field(default=None, min_length=1, max_length=200)


class FeedbackAnswers(BaseModel):
    model_config = ConfigDict(extra="forbid")
    a1_role: Literal["store_manager", "category", "supply_chain", "ecom_qcom_ops", "owner", "other"]
    a1_role_other: str | None = Short
    a2_business: Literal["kirana", "supermarket_chain", "quick_commerce", "ecom_marketplace", "distributor", "fmcg_brand", "other"]
    a2_business_other: str | None = Short
    a3_scale: Literal["1", "2_10", "11_50", "51_200", "over_200"] | None = None
    a4_online_food: Literal["yes", "planning", "no"] | None = None
    b1_frequency: Literal["rarely", "monthly", "weekly", "daily"] | None = None
    b2_writeoff_share: Literal["under_1", "1_3", "3_5", "5_10", "over_10", "dont_know"] | None = None
    b3_writeoff_value: Literal["under_10k", "10k_1l", "1l_10l", "10l_1cr", "over_1cr", "dont_know", "prefer_not"] | None = None
    b4_current_actions: list[Literal["blanket_markdown", "transfer", "return_supplier", "bundle", "staff_sale", "donate", "write_off", "nothing_systematic"]] | None = None
    b5_fssai: Literal["yes_limits", "yes_no_effect", "no", "not_sure"] | None = None
    b6_measurement: Literal["control_group", "before_after", "judgement", "dont_check"] | None = None
    c0_seen_demo: Literal["yes_live", "yes_video", "no"] | None = None
    c1_usefulness: int | None = Field(default=None, ge=1, le=5)
    c2_most_valuable: list[Literal["sellby_deadline", "targeted_offers", "human_approval", "holdout_measurement", "own_language"]] | None = Field(default=None, max_length=2)
    c3_blockers: list[Literal["data_integration", "trust_ai", "cost", "privacy_consent", "existing_tools", "staff_training", "other"]] | None = None
    c3_blockers_other: str | None = Short
    c4_pay_model: Literal["would_not_pay", "share_of_waste_avoided", "monthly_per_store", "one_time", "not_sure"] | None = None
    c5_pay_amount: Literal["under_1k", "1k_5k", "5k_20k", "over_20k"] | None = None
    d1_biggest_pain: str | None = Long
    d2_suggestion: str | None = Long
    e1_pilot: Literal["yes", "maybe", "no"] | None = None
    e2_quote_ok: Literal["yes", "no"] | None = None
    e3_contact: FeedbackContact | None = None
    e4_consent: Literal[True]


class FeedbackSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid")
    form_version: str = Field(pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}\.[0-9]+$")
    mode: Literal["self", "interview"]
    source: Literal["real", "test"]
    website: str | None = None
    answers: FeedbackAnswers
