"""Deterministic planning path: the same drafting/estimator/guardrail pipeline the stub model
drives (drafting.py + tools.py), run directly with no LLM in the loop.

Used by run.py as the fallback when the live model either exceeds its wall-clock deadline or
finishes without a valid play (`no_play`). This is not a workaround: the Cost Governor already
decides which gaps get a model call at all (governor.py, DECISIONS §18); this is the same
deterministic path applied when the model call was attempted but did not pay off in time. A play
produced this way is always labelled `planner_source: "deterministic_fallback"` in run_planner's
result -- it must never be presented as the model's own output.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from . import drafting
from . import tools as pt
from .context import PlannerContext


def deterministic_plan(ctx: PlannerContext, gap_id: str) -> dict[str, Any] | None:
    gap = pt.get_gap(gap_id)
    audiences = pt.get_candidate_audiences(gap["sku"], [gap["node_id"]], drafting.OBJECTIVE_BY_GAP[gap["type"]])
    candidates = drafting.candidate_mechanics(gap, ctx.policy_text)
    if not candidates:
        return None
    tenant = ctx.tenant
    holdout_fraction = float(tenant.thresholds.get("default_holdout_fraction", 0.10))
    min_treated_n = int(tenant.thresholds.get("min_treated_n", 20))
    languages = list(tenant.languages)
    drafts = [drafting.build_draft(gap, audiences, c, ctx.policy_version, ctx.run_id, holdout_fraction, min_treated_n, languages, ctx.as_of.isoformat()) for c in candidates]
    estimates = pt.estimate_outcomes(drafts)
    rejected: list[dict[str, Any]] = []
    tool_context = SimpleNamespace(state={}, actions=SimpleNamespace(escalate=False))
    for candidate, draft, est in zip(candidates, drafts, estimates, strict=True):
        if "error" in est:
            continue
        play = drafting.finish_draft(draft, gap, est, audiences, rejected, ctx.policy_text)
        result = pt.propose_play(play, tool_context)
        if result["valid"]:
            return play
        rejected.append({
            "mechanic": candidate["mechanic"], "mechanic_params": candidate.get("mechanic_params", {}),
            "expected_units": est["expected_outcome"]["units"], "expected_margin_inr": est["expected_outcome"]["margin_inr"],
            "rejected_because": "; ".join(result["errors"])[:400],
        })
    return None
