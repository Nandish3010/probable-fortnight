"""Cost Governor (DECISIONS §18.2): decides which gaps get a Planner run and what a play may cost.

Deterministic. Every figure is an estimate from config/models.toml [pricing] until the billing
export replaces it; the fields are labelled as such on the Play card.
"""
from __future__ import annotations

from typing import Any

from agents.gate.config import TenantConfig, load_models


def planner_eligible(gap: dict[str, Any], tenant: TenantConfig) -> tuple[bool, str]:
    threshold = float(tenant.thresholds.get("min_rupees_at_stake_for_planner", 500))
    if float(gap["rupees_at_stake"]) < threshold:
        return False, f"rupees at stake {gap['rupees_at_stake']:.0f} below planner threshold {threshold:.0f}; templated suggestion only"
    return True, f"rupees at stake {gap['rupees_at_stake']:.0f} >= threshold {threshold:.0f}"


def plan_cost_inr(loops: int = 3, cached: bool = True, batch: bool = False) -> float:
    p = load_models().get("pricing", {})
    tin = float(p.get("planner_tokens_in_per_loop", 6000)) * loops
    tout = float(p.get("planner_tokens_out_per_loop", 1500)) * loops
    usd = tin / 1e6 * float(p.get("usd_per_million_input", 0.75)) * ((1 - float(p.get("cached_input_discount", 0.9))) if cached else 1.0)
    usd += tout / 1e6 * float(p.get("usd_per_million_output", 3.75))
    if batch:
        usd *= float(p.get("batch_discount", 0.5))
    return round(usd * float(p.get("inr_per_usd", 83.0)), 2)


def cost_for_play(play: dict[str, Any], gap: dict[str, Any], tenant: TenantConfig, loops: int = 3) -> dict[str, float]:
    p = load_models().get("pricing", {})
    ceiling_pct = float(tenant.thresholds.get("cost_ceiling_pct_of_rupees_at_stake", 2.0))
    at_stake = float(gap["rupees_at_stake"])
    plan = plan_cost_inr(loops)
    audience = int(play["audience"]["size_after_consent"])
    expected_conversations = audience * 0.10
    wanted = expected_conversations * float(p.get("conversation_inr", 1.3))
    ceiling = max(0.0, at_stake * ceiling_pct / 100.0 - plan)
    budget = round(min(wanted, ceiling), 2)
    pct = round((plan + budget) / at_stake * 100.0, 3) if at_stake > 0 else 0.0
    return {"plan_cost_inr": plan, "conversation_budget_inr": budget, "pct_of_rupees_at_stake": pct}
