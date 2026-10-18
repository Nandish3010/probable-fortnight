"""Sealed-eval oracle: the best play the planner could legally have chosen for one gap. No model.

Definition (fixed in eval/sealed/PROTOCOL.md):

* RECOVERY of a candidate play is the product's headline figure, exactly: the estimator's
  `counterfactuals.do_nothing_inr + counterfactuals.play_net_inr` (the demo Tea play's 9,191.29, "recovered
  versus doing nothing"). Doing nothing recovers 0. The blanket 20% markdown baseline recovers
  `do_nothing_inr - blanket_markdown_inr` (Tea: 3,004.82). "Beats blanket" means recovery above that.
* LEGAL means accepted by `agents.planner.tools.propose_play` on the candidate as the planner's tools build it:
  JSON schema, pydantic model, `rederive_play` (audience and estimate overwritten by the tools), the online
  sell-by rule, all eight guardrails through `agents.gate.guardrails.check` with the tools' own
  `_guardrail_context`, and the runtime money invariant. The oracle calls `propose_play` itself, on a
  copy-on-write sandbox of the data directory, so no table of the real tenant is written.
* SCORE is the SAME `agents.gate.estimator.estimate` (through `agents.planner.tools._estimator_context`).

Action space (grid sizes are per gap; `grid_sizes` in the result gives the exact counts):

* mechanics: coupon, bundle (3 partners from `get_gap`), outlet_markdown, transfer_plus_nudge (every outlet in
  the cluster that `get_gap` lists), plus do-nothing and blanket markdown (the product's own counterfactual,
  evaluated at each markdown percentage; legal when that percentage clears the margin floor).
  Excluded, with the reason: `usual_order_addon`, `substitution`, `preorder` and `subscription_nudge`. They
  carry no discount, and the estimator's response rate does not depend on the mechanic (flat Beta prior), so
  an add-on is scored as a coupon at 0% off: an artefact that would dominate every real offer. The planner's
  own drafting (`agents/planner/drafting.py`) offers them only for stockout and slow-mover gaps.
* discount (coupon), markdown (outlet and blanket) and bundle discount off the list prices: 5% to 50% in steps
  of 5 (10 values). 5% is the smallest offer the oracle treats as an offer: the estimator's response rate is
  independent of the discount, so the unconstrained optimum is always 0% and would be a free coupon. The upper
  end is cut by the tenant margin floor (guardrail margin_floor), not by the grid.
* audience: the segments of `get_candidate_audiences`, sorted by consented size; every prefix of that order
  (1..n segments) plus every single segment (at most 2n-1 sets). Audience sizes come from
  `eligible_audience` (consent, frequency cap, subscriber filter), never from the model's figure.
* transfer: target node = each listed outlet; `transfer_units` = round(at_risk * f) for f in 0.05..1.00 step
  0.05, plus floor and ceil of the estimator's own expected units for each audience (the estimator caps units
  at `transfer_units`, so the optimum sits there).
* holdout fraction in {0.05, 0.10, 0.20, 0.30, 0.50, 0.90} (guardrail bounds [min_holdout_fraction, 0.9]);
  `min_treated_n` from the tenant config. The estimator does not read the holdout, so recovery is the same
  for every fraction; legality is still checked for the fraction chosen, and ties go to 0.10.

Search: all candidates are scored by the estimator, ordered by recovery (ties broken by a fixed key), and
the guardrail/legality check runs down that order until the best legal candidate of each mechanic is found.
Legality does not change a candidate's score, so this equals scoring the full grid and filtering.

cite_or_drop is a property of the rationale text, not of the action. The oracle writes the rationale the
stub planner writes (`drafting.finish_draft`, every number quoted from the draft's own fields); if the real
rule rejects it, the oracle writes a rationale with no numbers. Either way the rule is run by the real
`guardrails.check` inside `propose_play`; a candidate is never excluded because of its wording. Which
rationale was used is recorded in `rationale_kind`.

Limit, stated plainly: the oracle optimises the same estimator the planner is scored by. It measures decision
quality inside Taal's own economic model on a synthetic tenant, not real-world outcomes.
"""
from __future__ import annotations

import copy
import dataclasses
import math
import os
import shutil
import tempfile
from collections.abc import Iterable
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from agents.gate import guardrails as gr
from agents.gate.estimator import estimate
from agents.planner import drafting
from agents.planner import tools as pt
from agents.planner.context import PlannerContext, reset_context, set_context
from agents.planner.governor import planner_eligible

DISCOUNT_GRID = tuple(range(5, 55, 5))
HOLDOUT_GRID = (0.05, 0.10, 0.20, 0.30, 0.50, 0.90)
DEFAULT_HOLDOUT = 0.10
TRANSFER_FRACTIONS = tuple(round(0.05 * i, 2) for i in range(1, 21))
MECH_ORDER = ("transfer_plus_nudge", "bundle", "coupon", "outlet_markdown", "blanket_markdown", "do_nothing")
TIE_EPS = 0.005  # INR: recoveries equal to the paisa are ties
RATIONALE_BARE = "Highest projected recovery among the candidates that pass every guardrail; figures are in expected_outcome and counterfactuals."


# ----------------------------------------------------------------------------- helpers

def recovery_of(est: dict[str, Any]) -> float:
    """The hero figure: recovered versus doing nothing."""
    cf = est["counterfactuals"]
    return round(float(cf["do_nothing_inr"]) + float(cf["play_net_inr"]), 2)


def blanket_recovery(est_or_cf: dict[str, Any]) -> float:
    cf = est_or_cf.get("counterfactuals", est_or_cf)
    return round(float(cf["do_nothing_inr"]) - float(cf["blanket_markdown_inr"]), 2)


def segment_sets(audiences: list[dict[str, Any]]) -> list[tuple[str, ...]]:
    segs = [a["segment_id"] for a in audiences if a["size_after_consent"] > 0] or [a["segment_id"] for a in audiences[:1]]
    out: list[tuple[str, ...]] = []
    for k in range(len(segs), 0, -1):  # full set first
        out.append(tuple(segs[:k]))
    for s in segs:
        if (s,) not in out:
            out.append((s,))
    return out


def _params_key(params: dict[str, Any]) -> str:
    return repr(sorted(params.items()))


def _cand_sort_key(c: dict[str, Any]) -> tuple:
    return (-round(c["recovery"], 2), MECH_ORDER.index(c["class"]), c["seg_index"], _params_key(c["mechanic_params"]), abs(c["holdout"] - DEFAULT_HOLDOUT), c["holdout"])


def _is_discount(mechanic: str) -> bool:
    return mechanic in pt.DISCOUNT_MECHANICS


def _cached_store_classes():
    from agents.gate.store import LocalStore, OverlayStore

    class CachedLocal(LocalStore):
        """LocalStore that parses each table once. Same rows, same order; only the repeated JSON parsing is saved."""

        def __init__(self, root: str | Path):
            super().__init__(root)
            self._cache: dict[str, list[dict[str, Any]]] = {}

        def read(self, table: str) -> list[dict[str, Any]]:
            if table not in self._cache:
                self._cache[table] = LocalStore.read(self, table)
            return self._cache[table]

        def write(self, table: str, rows: Iterable[dict[str, Any]]) -> None:
            self._cache.pop(table, None)
            super().write(table, rows)

        def append(self, table: str, rows: Iterable[dict[str, Any]]) -> None:
            self._cache.pop(table, None)
            super().append(table, rows)

    class CachedOverlay(OverlayStore):
        def __init__(self, base: CachedLocal, overlay_root: str | Path):
            super().__init__(base.root, overlay_root)
            self._base_cached = base
            self._touched: set[str] = set()

        def read(self, table: str) -> list[dict[str, Any]]:
            if table in self._touched:
                return OverlayStore.read(self, table)
            return self._base_cached.read(table)

        def write(self, table: str, rows: Iterable[dict[str, Any]]) -> None:
            rows = list(rows)
            super().write(table, rows)
            self._touched.add(table)

        def append(self, table: str, rows: Iterable[dict[str, Any]]) -> None:
            rows = list(rows)
            super().append(table, rows)
            self._touched.add(table)

    return CachedLocal, CachedOverlay


def cached_context(data_dir: str | Path, run_id: str) -> PlannerContext:
    """A PlannerContext over the same data with parse-once reads (the oracle makes thousands of reads)."""
    cached_local, _ = _cached_store_classes()
    ctx = PlannerContext.build(data_dir, run_id=run_id)
    ctx.store = cached_local(data_dir)
    return ctx


class _Sandbox:
    """Copy-on-write view of the tenant data dir for propose_play's writes."""

    def __init__(self, base_store: Any):
        _, cached_overlay = _cached_store_classes()
        self.tmp = tempfile.mkdtemp(prefix="taal_oracle_")
        self.store = cached_overlay(base_store, self.tmp)

    def close(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)


def _build_draft(ctx: PlannerContext, gap: dict[str, Any], audiences: list[dict[str, Any]], candidate: dict[str, Any], segs: tuple[str, ...], holdout: float) -> dict[str, Any]:
    min_treated_n = int(ctx.tenant.thresholds.get("min_treated_n", 20))
    draft = drafting.build_draft(gap, audiences, candidate, ctx.policy_version, ctx.run_id, holdout, min_treated_n, list(ctx.tenant.languages), ctx.as_of.isoformat())
    draft["audience"]["segment_ids"] = list(segs)
    return draft


# ----------------------------------------------------------------------------- the oracle

def enumerate_candidates(ctx: PlannerContext, gap_id: str) -> dict[str, Any]:
    """Stage 1: every candidate in the grid with its estimator recovery. Needs the context set."""
    gap = pt.get_gap(gap_id)
    node_type = (gap.get("node") or {}).get("type")
    audiences = pt.get_candidate_audiences(gap["sku"], [gap["node_id"]], drafting.OBJECTIVE_BY_GAP[gap["type"]], gap_id=gap_id)
    sets = segment_sets(audiences)
    partners = gap.get("bundle_partner_candidates") or []
    outlets = gap.get("transfer_candidates") or []
    list_price = float(gap["product"]["list_price"])
    sellby_passed = bool((gap.get("evidence") or {}).get("sellby_passed")) or (gap["deadline_type"] == "online_sellby" and gap["deadline_date"] < ctx.as_of.isoformat())
    uar = int(gap["units_at_risk"])

    # audience sizes per (segment set, discount-class); these are the tools' own numbers
    sizes: dict[tuple[tuple[str, ...], bool], int] = {}
    probe_c = {"mechanic": "coupon", "mechanic_params": {"discount_pct": DISCOUNT_GRID[0]}}
    probe_t = {"mechanic": "transfer_plus_nudge", "mechanic_params": {"transfer_to_node": (outlets[0]["node_id"] if outlets else "OUT-00"), "transfer_units": uar}}
    for segs in sets:
        for cls, probe in ((True, probe_c), (False, probe_t)):
            d = _build_draft(ctx, gap, audiences, probe, segs, DEFAULT_HOLDOUT)
            sizes[(segs, cls)] = len(pt.eligible_audience(ctx, d)[1])

    cache: dict[tuple, dict[str, Any]] = {}
    base_ectx: dict[str | None, Any] = {}

    def scored(draft: dict[str, Any], size: int, partner_sku: str | None) -> dict[str, Any]:
        params = {k: v for k, v in draft["mechanic_params"].items() if k != "transfer_to_node"}  # the estimator never reads the node
        key = (draft["mechanic"], _params_key(params), size, partner_sku)
        if key not in cache:
            if partner_sku not in base_ectx:  # the context reads order lines and priors: build it once per bundle partner
                base_ectx[partner_sku] = pt._estimator_context(ctx, draft)
            cache[key] = estimate(draft, dataclasses.replace(base_ectx[partner_sku], audience_size_after_consent=size))
        return cache[key]

    cands: list[dict[str, Any]] = []
    n_grid = {"coupon": 0, "outlet_markdown": 0, "bundle": 0, "transfer_plus_nudge": 0}

    def add(cls: str, mechanic: str, params: dict[str, Any], si: int, segs: tuple[str, ...], est: dict[str, Any], size: int) -> None:
        for h in HOLDOUT_GRID:
            cands.append({"class": cls, "mechanic": mechanic, "mechanic_params": params, "segments": list(segs), "seg_index": si, "holdout": h, "audience_after_consent": size, "recovery": recovery_of(est), "est": est})

    for si, segs in enumerate(sets):
        sz_d, sz_t = sizes[(segs, True)], sizes[(segs, False)]
        if not sellby_passed:
            for pct in DISCOUNT_GRID:
                c = {"mechanic": "coupon", "mechanic_params": {"discount_pct": pct}}
                d = _build_draft(ctx, gap, audiences, c, segs, DEFAULT_HOLDOUT)
                add("coupon", "coupon", c["mechanic_params"], si, segs, scored(d, sz_d, None), sz_d)
            for p in partners:
                for pct in DISCOUNT_GRID:
                    price = round((list_price + float(p["list_price"])) * (1 - pct / 100.0), 0)
                    c = {"mechanic": "bundle", "mechanic_params": {"bundle_sku": p["sku"], "bundle_price": price}}
                    d = _build_draft(ctx, gap, audiences, c, segs, DEFAULT_HOLDOUT)
                    add("bundle", "bundle", c["mechanic_params"], si, segs, scored(d, sz_d, p["sku"]), sz_d)
        for pct in DISCOUNT_GRID:
            c = {"mechanic": "outlet_markdown", "mechanic_params": {"markdown_pct": pct}}
            d = _build_draft(ctx, gap, audiences, c, segs, DEFAULT_HOLDOUT)
            add("outlet_markdown", "outlet_markdown", c["mechanic_params"], si, segs, scored(d, sz_d, None), sz_d)
        if outlets:
            c0 = {"mechanic": "transfer_plus_nudge", "mechanic_params": {"transfer_to_node": outlets[0]["node_id"], "transfer_units": uar}}
            d0 = _build_draft(ctx, gap, audiences, c0, segs, DEFAULT_HOLDOUT)
            u = float(scored(d0, sz_t, None)["expected_outcome"]["units"])
            tus = sorted({max(1, round(uar * f)) for f in TRANSFER_FRACTIONS} | {t for t in (math.floor(u), math.ceil(u)) if 1 <= t <= uar})
            for o in outlets:
                for tu in tus:
                    c = {"mechanic": "transfer_plus_nudge", "mechanic_params": {"transfer_to_node": o["node_id"], "transfer_units": tu}}
                    d = _build_draft(ctx, gap, audiences, c, segs, DEFAULT_HOLDOUT)
                    add("transfer_plus_nudge", "transfer_plus_nudge", c["mechanic_params"], si, segs, scored(d, sz_t, None), sz_t)

    # blanket markdown at each percentage: the product's own counterfactual formula
    base_c = {"mechanic": "outlet_markdown", "mechanic_params": {"markdown_pct": 20}}
    d_b = _build_draft(ctx, gap, audiences, base_c, sets[0], DEFAULT_HOLDOUT)
    for pct in DISCOUNT_GRID:
        d = copy.deepcopy(d_b)
        d["mechanic_params"] = {"markdown_pct": pct}
        est = scored(d, sizes[(sets[0], True)], None)
        cands.append({"class": "blanket_markdown", "mechanic": "outlet_markdown", "mechanic_params": {"markdown_pct": pct}, "segments": [], "seg_index": 0, "holdout": DEFAULT_HOLDOUT, "audience_after_consent": 0, "recovery": blanket_recovery(est), "est": est})
    cands.append({"class": "do_nothing", "mechanic": None, "mechanic_params": {}, "segments": [], "seg_index": 0, "holdout": DEFAULT_HOLDOUT, "audience_after_consent": 0, "recovery": 0.0, "est": None})

    for c in cands:
        if c["class"] in n_grid:
            n_grid[c["class"]] += 1
    n_grid = {k: v // len(HOLDOUT_GRID) for k, v in n_grid.items()}  # holdout is a multiplier, reported separately
    base = scored(d_b, sizes[(sets[0], True)], None)
    return {
        "gap": gap, "audiences": audiences, "candidates": sorted(cands, key=_cand_sort_key),
        "blanket20": blanket_recovery(base), "blanket20_pct": base["counterfactuals"]["blanket_markdown_pct"],
        "grid_sizes": {**n_grid, "segment_sets": len(sets), "holdout_values": len(HOLDOUT_GRID), "discount_values": len(DISCOUNT_GRID), "transfer_nodes": len(outlets), "bundle_partners": len(partners), "total_with_holdout": sum(1 for c in cands if c["class"] in n_grid)},
        "sellby_passed": sellby_passed, "node_type": node_type,
    }


def _margin_floor_ok(ctx: PlannerContext, enum: dict[str, Any], cand: dict[str, Any], cache: dict[tuple, bool]) -> bool:
    """The real margin_floor guardrail on the candidate's mechanic and params (it reads nothing else). A cheap
    exact pre-filter: a candidate that fails it cannot pass `guardrails.check`, so it is not sent to propose_play."""
    key = (cand["mechanic"], _params_key(cand["mechanic_params"]))
    if key not in cache:
        draft = _build_draft(ctx, enum["gap"], enum["audiences"], {"mechanic": cand["mechanic"], "mechanic_params": dict(cand["mechanic_params"])}, tuple(cand["segments"]), cand["holdout"])
        gctx = pt._guardrail_context(ctx, draft)
        cache[key] = bool(gr.RULES["margin_floor"](draft, gctx)["passed"])
    return cache[key]


def legal_play(ctx: PlannerContext, sandbox_ctx: PlannerContext, enum: dict[str, Any], cand: dict[str, Any]) -> dict[str, Any]:
    """Stage 2: run the candidate through the product's own propose_play. Returns the verdict and the play."""
    gap, audiences = enum["gap"], enum["audiences"]
    c = {"mechanic": cand["mechanic"], "mechanic_params": dict(cand["mechanic_params"])}
    draft = _build_draft(ctx, gap, audiences, c, tuple(cand["segments"]), cand["holdout"])
    last: dict[str, Any] = {}
    for kind in ("tool_style", "bare"):
        est = pt._estimate_one(ctx, draft)
        if "error" in est:
            return {"legal": False, "errors": [est["error"]], "play": None, "rationale_kind": kind}
        play = drafting.finish_draft(draft, gap, est, audiences, [], ctx.policy_text)
        if kind == "bare":
            play["rationale"] = RATIONALE_BARE
        tc = SimpleNamespace(state={}, actions=SimpleNamespace(escalate=False))
        token = set_context(sandbox_ctx)
        try:
            res = pt.propose_play(copy.deepcopy(play), tc)
        finally:
            reset_context(token)
        rows = sandbox_ctx.store.find("plays", play_id=play["play_id"]) if res["valid"] else []
        if res["valid"]:
            import json

            final = json.loads(rows[-1]["play_json"])
            return {"legal": True, "errors": [], "play": final, "rationale_kind": kind}
        last = {"legal": False, "errors": res["errors"], "play": None, "rationale_kind": kind}
        if not any("cite_or_drop" in e for e in res["errors"]):
            break
    return last


def _public(c: dict[str, Any], v: dict[str, Any] | None = None) -> dict[str, Any]:
    out = {"class": c["class"], "mechanic": c["mechanic"], "mechanic_params": c["mechanic_params"], "segments": c["segments"], "holdout_fraction": c["holdout"], "audience_after_consent": c["audience_after_consent"], "recovery_inr": c["recovery"]}
    if c["est"] is not None:
        out["expected_outcome"] = c["est"]["expected_outcome"]
        out["counterfactuals"] = c["est"]["counterfactuals"]
    if v is not None:
        out["legal"] = v["legal"]
        out["rationale_kind"] = v["rationale_kind"]
        if v["play"] is not None:
            out["guardrails"] = [{"rule": g["rule"], "passed": g["passed"]} for g in v["play"]["guardrails"]]
            out["recovery_inr_play"] = recovery_of(v["play"])
    return out


def solve_gap(data_dir: str | Path, gap_id: str, ctx: PlannerContext | None = None) -> dict[str, Any]:
    """The oracle for one gap: best legal candidate per mechanic, the top 3 mechanics, and the baselines."""
    data_dir = Path(data_dir)
    ctx = ctx or cached_context(data_dir, f"oracle_{gap_id}")
    sb = _Sandbox(ctx.store)
    sctx = dataclasses.replace(ctx, store=sb.store)
    token = set_context(ctx)
    try:
        gap_row = ctx.store.find("gaps", gap_id=gap_id)[-1]
        eligible, why = planner_eligible(gap_row, ctx.tenant)
        enum = enumerate_candidates(ctx, gap_id)
        by_class: dict[str, dict[str, Any]] = {}
        checked = pruned = 0
        mf_cache: dict[tuple, bool] = {}
        for cand in enum["candidates"]:
            if cand["class"] in by_class:
                continue
            if cand["class"] == "do_nothing":
                by_class["do_nothing"] = _public(cand, {"legal": True, "rationale_kind": "n/a", "play": None})
                continue
            if cand["class"] == "blanket_markdown":
                # not a planner play: legal when the markdown clears the category margin floor (the same rule, via guardrails.RULES)
                gctx = pt._guardrail_context(ctx, _build_draft(ctx, enum["gap"], enum["audiences"], {"mechanic": "outlet_markdown", "mechanic_params": cand["mechanic_params"]}, tuple(enum["candidates"][0]["segments"] or [enum["audiences"][0]["segment_id"]]), DEFAULT_HOLDOUT))
                ok = gr.RULES["margin_floor"]({"mechanic": "outlet_markdown", "mechanic_params": cand["mechanic_params"]}, gctx)["passed"]
                checked += 1
                if ok:
                    by_class["blanket_markdown"] = _public(cand, {"legal": True, "rationale_kind": "n/a", "play": None})
                continue
            if not _margin_floor_ok(ctx, enum, cand, mf_cache):
                pruned += 1  # the real margin_floor rule fails, so guardrails.check (hence propose_play) fails too
                continue
            v = legal_play(ctx, sctx, enum, cand)
            checked += 1
            if v["legal"]:
                by_class[cand["class"]] = _public(cand, v)
        ranked = sorted(by_class.values(), key=lambda p: (-round(p["recovery_inr"], 2), MECH_ORDER.index(p["class"])))
        # ties (to the paisa) all count as best; the first in MECH_ORDER is reported first
        top = ranked[:3]
        best = ranked[0]
        tied = [p["class"] for p in ranked if abs(p["recovery_inr"] - best["recovery_inr"]) < TIE_EPS]
        runner_up = ranked[1]["recovery_inr"] if len(ranked) > 1 else 0.0
        return {
            "gap_id": gap_id, "planner_eligible": eligible, "eligibility_reason": why,
            "sku": gap_row["sku"], "node_id": gap_row["node_id"], "gap_type": gap_row["type"], "units_at_risk": gap_row["units_at_risk"], "rupees_at_stake": gap_row["rupees_at_stake"],
            "blanket20_recovery_inr": enum["blanket20"], "do_nothing_recovery_inr": 0.0,
            "best": best, "best_classes_tied": tied, "top3": top, "per_class_best": by_class,
            "gap_to_runner_up": (best["recovery_inr"] - runner_up) / best["recovery_inr"] if best["recovery_inr"] > 0 else None,
            "grid_sizes": enum["grid_sizes"], "sellby_passed": enum["sellby_passed"], "legality_checks_run": checked, "pruned_by_margin_floor": pruned,
        }
    finally:
        reset_context(token)
        sb.close()


def solve_gaps(data_dir: str | Path, gap_ids: Iterable[str]) -> dict[str, dict[str, Any]]:
    ctx = cached_context(data_dir, "oracle_pool")
    out = {}
    for gid in gap_ids:
        out[gid] = solve_gap(data_dir, gid, ctx)
    return out


if __name__ == "__main__":  # python -m eval.sealed.oracle <data_dir> <gap_id>
    import json
    import sys

    os.environ.setdefault("TAAL_MODEL_BACKEND", "stub")
    print(json.dumps(solve_gap(sys.argv[1], sys.argv[2]), indent=1, default=str))
