#!/usr/bin/env python3
"""Docs truth sweep (2026-09-27), Task 1: "Impact in numbers".

Deterministic, Python-stdlib-only. Reads ONLY these committed repo files (no network, no
.local/, no scratch tenant):
  - eval/raw/portfolio_2026-09-24.json   (nightly portfolio job output, committed)
  - eval/raw/cost_measurement_2026-09-23.json (measured-cost job output, committed)
  - agents/gate/estimator.py             (imported directly, to read its real constants
                                           rather than transcribe its docstring by hand)
  - agents/planner/tools.py              (read as text, only to cite the line that wires
                                           tenant.thresholds.transfer_cost_per_unit_inr into
                                           the estimator context -- not executed)
  - config/tenant.demo.toml              (parsed with stdlib tomllib)
  - docs/impact_math.md, docs/DECISIONS.md (read as text, for citation + Part-3 cross-check)

Writes impact_numbers.json next to this script and prints it to stdout.

Run from anywhere with:
    python3 eval/raw/docs_truth_sweep_2026-09-27/impact_numbers.py
"""
from __future__ import annotations

import json
import sys
import tomllib
from pathlib import Path

THIS_FILE = Path(__file__).resolve()
REPO_ROOT = THIS_FILE.parents[3]  # .../eval/raw/docs_truth_sweep_2026-09-27/impact_numbers.py -> repo root
OUT_PATH = THIS_FILE.with_name("impact_numbers.json")

PORTFOLIO_PATH = REPO_ROOT / "eval/raw/portfolio_2026-09-24.json"
COST_PATH = REPO_ROOT / "eval/raw/cost_measurement_2026-09-23.json"
ESTIMATOR_PATH = REPO_ROOT / "agents/gate/estimator.py"
PLANNER_TOOLS_PATH = REPO_ROOT / "agents/planner/tools.py"
TENANT_TOML_PATH = REPO_ROOT / "config/tenant.demo.toml"
IMPACT_MATH_PATH = REPO_ROOT / "docs/impact_math.md"
DECISIONS_PATH = REPO_ROOT / "docs/DECISIONS.md"
GAPS_PY_PATH = REPO_ROOT / "jobs/sense/gaps.py"
FORECAST_PY_PATH = REPO_ROOT / "jobs/sense/forecast.py"

for p in (PORTFOLIO_PATH, COST_PATH, ESTIMATOR_PATH, PLANNER_TOOLS_PATH, TENANT_TOML_PATH,
          IMPACT_MATH_PATH, DECISIONS_PATH, GAPS_PY_PATH, FORECAST_PY_PATH):
    if not p.is_file():
        raise SystemExit(f"missing committed input file: {p}")

sys.path.insert(0, str(REPO_ROOT))
from agents.gate import estimator as estimator_module  # noqa: E402


def _r2(x: float) -> float:
    return round(float(x), 2)


def _line_of(path: Path, pattern: str) -> str:
    """1-based line number of the first line matching `pattern` (a plain substring), as 'path:line'
    relative to the repo root. Fails loudly if not found, rather than guessing."""
    text = path.read_text(encoding="utf-8")
    for i, line in enumerate(text.splitlines(), start=1):
        if pattern in line:
            return f"{path.relative_to(REPO_ROOT)}:{i}"
    raise SystemExit(f"pattern not found in {path}: {pattern!r}")


def _json_path(path: Path, pointer: str) -> str:
    return f"{path.relative_to(REPO_ROOT)}#{pointer}"


# --------------------------------------------------------------------------------------- load

portfolio = json.loads(PORTFOLIO_PATH.read_text(encoding="utf-8"))
cost = json.loads(COST_PATH.read_text(encoding="utf-8"))
tenant_toml = tomllib.loads(TENANT_TOML_PATH.read_text(encoding="utf-8"))
impact_math_text = IMPACT_MATH_PATH.read_text(encoding="utf-8")
decisions_text = DECISIONS_PATH.read_text(encoding="utf-8")

plays = portfolio["plays"]
totals = portfolio["totals"]
governor = portfolio["governor"]
planned = portfolio["planned"]

assert len(plays) == planned["count"], "plays array length must match planned.count"

# --------------------------------------------------------------------------------------- (a) exposure / horizon

# The portfolio file has no `horizon_days` field of its own (checked: no key containing
# "horizon" or "day" anywhere in eval/raw/portfolio_2026-09-24.json). The Sense gap-detection
# horizon that bounds which gaps this run *could* surface is a code constant, HORIZON = 28,
# consumed by jobs/sense/gaps.py to build `horizon_end` for online_sellby_breach /
# expiry_writeoff / slow_mover / rebalance gaps. stockout_risk, unmet_demand and assortment_gap
# instead use each node's own lead_time_days as their deadline, not this fixed horizon.
horizon_const_line = _line_of(FORECAST_PY_PATH, "HORIZON = 28")
horizon_use_line = _line_of(GAPS_PY_PATH, "horizon_end = as_of + timedelta(days=HORIZON - 1)")
horizon_gate_line = _line_of(GAPS_PY_PATH, "if deadline > horizon_end:")
horizon_stockout_line = _line_of(GAPS_PY_PATH, "lead_end = as_of + timedelta(days=lead)")
horizon_unmet_line = _line_of(GAPS_PY_PATH, "deadline = as_of + timedelta(days=lead)")
horizon_assortment_line = _line_of(GAPS_PY_PATH, "deadline = as_of + timedelta(days=int(node[\"lead_time_days\"]))")

week_phrase_line = None
for i, line in enumerate(impact_math_text.splitlines(), start=1):
    if "this week alone" in line:
        week_phrase_line = i
        break

exposure_entry = {
    "value": totals["exposure_inr"],
    "unit": "INR",
    "label": "seeded",
    "source": _json_path(PORTFOLIO_PATH, "/totals/exposure_inr"),
    "note": (
        f"Sum of rupees_at_stake across every one of the {totals['gaps']} gaps from Sense run "
        f"{portfolio['sense_run_id']} (as_of {portfolio['as_of']}), computed deterministically "
        "from the seeded tenant's generated inventory/forecast data with no assumed customer "
        "response rate -- this is total exposure across ALL gaps, not just the 424 the planner "
        "drafted a play for (127 were triaged out below the Rs 500 threshold, 4 eligible gaps got "
        "no valid play). Matches docs/impact_math.md Part 3 'Total exposure' row exactly."
    ),
}

horizon_entry = {
    "value": None,
    "unit": "days",
    "label": "synthetic",
    "source": (
        f"eval/raw/portfolio_2026-09-24.json has no horizon_days field (checked: no key containing "
        f"'horizon' anywhere in the file); {horizon_const_line} (HORIZON = 28)"
    ),
    "note": (
        "The portfolio file itself does not state a horizon. The underlying Sense gap-detection "
        "horizon is a 28-day code constant (jobs/sense/forecast.py: HORIZON = 28), used at "
        f"{horizon_use_line} to build horizon_end=as_of+27d, and gated at {horizon_gate_line} for "
        "online_sellby_breach/expiry_writeoff/slow_mover/rebalance gaps only -- consistent with "
        "docs/DECISIONS.md:177 ('horizon 28'). stockout_risk uses each node's own lead_time_days "
        f"instead ({horizon_stockout_line}), as do unmet_demand ({horizon_unmet_line}) and "
        f"assortment_gap ({horizon_assortment_line}), so 'the portfolio's horizon' is not one "
        "single number across all 6 gap types that produced exposure this run. "
        + (
            f"docs/impact_math.md:{week_phrase_line} describes the same Rs 1.8M total exposure "
            "figure as 'this week alone' (a 7-day framing); that does not match the 28-day "
            "gap-detection horizon that actually bounds online_sellby_breach/expiry_writeoff/"
            "slow_mover/rebalance gaps (66% of this run's gaps by count), so if the horizon is "
            "meant to read as 28 days, 'this week alone' is the wrong framing -- flagged, not fixed "
            "(docs are out of scope for this evidence file)."
            if week_phrase_line
            else "Could not find the phrase 'this week alone' in docs/impact_math.md to cross-check."
        )
    ),
}

# --------------------------------------------------------------------------------------- (b) plays_planned

by_mechanic: dict[str, int] = {}
for p in plays:
    by_mechanic[p["mechanic"]] = by_mechanic.get(p["mechanic"], 0) + 1
assert sum(by_mechanic.values()) == len(plays)

plays_planned_entry = {
    "value": len(plays),
    "unit": "plays",
    "label": "seeded",
    "source": _json_path(PORTFOLIO_PATH, "/planned/count (== len(/plays))"),
    "note": (
        "planned.count and len(plays) agree (424). Every play is the deterministic drafter's "
        "output for one planner-eligible gap (agents/planner/deterministic.py via jobs/portfolio/"
        "run.py), not a model call."
    ),
    "by_mechanic": dict(sorted(by_mechanic.items(), key=lambda kv: -kv[1])),
}

# --------------------------------------------------------------------------------------- (c) margin split
#
# Rule applied, per agents/gate/estimator.py's own module docstring (not this prompt's wording):
#   transfer_plus_nudge : margin = waste_avoided_inr - transfer_cost_per_unit * transfer_units
#                          (a write-off-avoided-minus-transfer-cost formula; does not scale with
#                          a list/net "selling price" at all)
#   every other mechanic (coupon, outlet_markdown, bundle are named explicitly; "other mechanics"
#   covers the rest -- preorder, usual_order_addon, substitution, subscription_nudge all appear or
#   could appear in this portfolio) : margin = units * (net_price - unit_cost), i.e. margin scales
#   with units actually sold at some price -- a "selling units" formula.
# This is also exactly the code's own branch in estimate(): `if mechanic == "transfer_plus_nudge":
# ... else: margin = units * econ["margin"]` (agents/gate/estimator.py). So the split below is
# transfer_plus_nudge vs. everything else, matching both the docstring's rule and the code path.

docstring_transfer_line = _line_of(
    ESTIMATOR_PATH, 'transfer_plus_nudge: margin = waste_avoided_inr - transfer_cost_per_unit * transfer_units'
)
docstring_other_line = _line_of(ESTIMATOR_PATH, "other mechanics    : margin = units * (list_price - unit_cost)")
code_branch_line = _line_of(ESTIMATOR_PATH, 'if mechanic == "transfer_plus_nudge":')
code_else_margin_line = _line_of(ESTIMATOR_PATH, 'margin = units * econ["margin"]')

sales_margin = sum(p["expected_outcome"]["margin_inr"] for p in plays if p["mechanic"] != "transfer_plus_nudge")
writeoff_avoided_net_of_transfer = sum(p["expected_outcome"]["margin_inr"] for p in plays if p["mechanic"] == "transfer_plus_nudge")
expected_margin_total_reported = planned["expected_margin_inr"]
margin_sum_check_value = _r2(sales_margin + writeoff_avoided_net_of_transfer)
margin_sum_ok = abs(margin_sum_check_value - expected_margin_total_reported) < 0.01

expected_margin_total_entry = {
    "value": expected_margin_total_reported,
    "unit": "INR",
    "label": "projected",
    "source": _json_path(PORTFOLIO_PATH, "/planned/expected_margin_inr"),
    "note": (
        "Sum of expected_outcome.margin_inr over all 424 planned plays; an expectation under the "
        "estimator's default 5% response-rate prior (see default_response_prior below), not a "
        "measured outcome -- no play in this portfolio run has been approved or measured."
    ),
}
planner_tools_transfer_line = _line_of(PLANNER_TOOLS_PATH, 'transfer_cost_per_unit=float(ctx.tenant.thresholds.get(')

sales_margin_entry = {
    "value": _r2(sales_margin),
    "unit": "INR",
    "label": "projected",
    "source": _json_path(PORTFOLIO_PATH, "/plays[*]/expected_outcome/margin_inr (summed over mechanic != 'transfer_plus_nudge')"),
    "note": (
        f"Plays whose margin the estimator computes by selling units at some net price "
        f"(coupon, outlet_markdown, bundle, and the docstring's 'other mechanics' catch-all -- "
        f"{docstring_other_line}, code branch {code_else_margin_line}). Mechanics present in this "
        "portfolio: "
        + ", ".join(f"{m} ({n})" for m, n in sorted(by_mechanic.items(), key=lambda kv: -kv[1]) if m != "transfer_plus_nudge")
        + "."
    ),
}
writeoff_avoided_entry = {
    "value": _r2(writeoff_avoided_net_of_transfer),
    "unit": "INR",
    "label": "projected",
    "source": _json_path(PORTFOLIO_PATH, "/plays[*]/expected_outcome/margin_inr (summed over mechanic == 'transfer_plus_nudge')"),
    "note": (
        f"transfer_plus_nudge plays only ({by_mechanic.get('transfer_plus_nudge', 0)} of them): the "
        f"estimator defines this mechanic's margin as waste_avoided_inr minus the per-unit transfer "
        f"cost ({docstring_transfer_line}, code {code_branch_line}), not as units sold at a price. "
        f"transfer_cost_per_unit_inr = "
        f"{tenant_toml['thresholds']['transfer_cost_per_unit_inr']} in config/tenant.demo.toml, "
        f"identical to the estimator's own DEFAULT_TRANSFER_COST_PER_UNIT = "
        f"{estimator_module.DEFAULT_TRANSFER_COST_PER_UNIT}; the planner wires the tenant value in "
        f"at {planner_tools_transfer_line}, "
        "so both sources agree and there is no silent divergence."
    ),
}
margin_sum_check_entry = {
    "value": margin_sum_check_value,
    "unit": "INR",
    "label": "projected",
    "source": "computed in this script from the two sums above",
    "note": (
        f"sales_margin + writeoff_avoided_net_of_transfer = {sales_margin_entry['value']} + "
        f"{writeoff_avoided_entry['value']} = {margin_sum_check_value}, vs. planned.expected_margin_inr "
        f"= {expected_margin_total_reported} in the portfolio file. Match within Rs 0.01: {margin_sum_ok}."
    ),
    "assertion_passed": margin_sum_ok,
}
if not margin_sum_ok:
    raise SystemExit(f"margin sum check FAILED: {margin_sum_check_entry}")

# --------------------------------------------------------------------------------------- (d) monthly_cost

modeled = cost["modeled"]
monthly_cost_entry = {
    "value": modeled["total_inr"],
    "unit": "INR",
    "label": "measured",
    "source": _json_path(COST_PATH, "/modeled/total_inr"),
    "note": (
        "Measured (usage), list-priced; not a bill -- usage quantities measured over the trailing "
        "30 days, priced at Google's public list rates. "
        f"Covers: {', '.join(sorted(modeled['lines'].keys()))} (Vertex AI Gemini tokens, BigQuery "
        f"query bytes billed, BigQuery active storage, Cloud Run vCPU/GiB-seconds, Firestore "
        f"read/write/delete units). Period: trailing {modeled['window_days']} days from "
        f"{cost['measured_at']} for every line except bigquery_storage, which the file itself "
        f"labels a real point-in-time snapshot, not usage over the window "
        f"({_json_path(COST_PATH, '/modeled/lines/bigquery_storage/note')}). "
        f"Method, in the file's own words: '{modeled['methodology']}' -- "
        f"'{modeled['methodology_note']}'. "
        f"So: the USAGE QUANTITIES (tokens, bytes, vcpu-seconds, read/write units) are measured "
        f"real telemetry for project {cost['project']}; the RUPEE TOTAL "
        f"(total_usd={modeled['total_usd']}, total_inr={modeled['total_inr']}) is those quantities "
        f"priced at Google's public list rates checked {modeled['rates_used']['checked_at']} "
        f"(usd_to_inr={modeled['rates_used']['usd_to_inr']}), explicitly NOT an actual "
        f"billing-dollar figure -- {cost['reason']} "
        f"cost_per_play_inr is {modeled['cost_per_play_inr']!r}: "
        f"{modeled['cost_per_play_reason']}"
    ),
}

# --------------------------------------------------------------------------------------- (e) default_response_prior

prior_n_values = sorted({p["expected_outcome"]["prior_n"] for p in plays})
measured_n_values = sorted({p["expected_outcome"]["measured_n"] for p in plays})
code_default_sum = estimator_module.DEFAULT_ALPHA + estimator_module.DEFAULT_BETA
default_alpha_line = _line_of(ESTIMATOR_PATH, "DEFAULT_ALPHA = ")
default_beta_line = _line_of(ESTIMATOR_PATH, "DEFAULT_BETA = ")
prior_n_matches_default = prior_n_values == [code_default_sum]

default_response_prior_entry = {
    "value": {
        "mean": round(estimator_module.DEFAULT_ALPHA / code_default_sum, 4),
        "alpha": estimator_module.DEFAULT_ALPHA,
        "beta": estimator_module.DEFAULT_BETA,
    },
    "unit": "probability (mean); pseudo-counts (alpha, beta)",
    "label": "synthetic",
    "source": f"{default_alpha_line}; {default_beta_line}",
    "note": (
        "The portfolio file does not carry a named default_alpha/default_beta field. Cross-check: "
        f"expected_outcome.prior_n (= alpha+beta at estimate time) takes exactly one distinct value "
        f"across all {len(plays)} plays in the portfolio file: {prior_n_values}, "
        f"and expected_outcome.measured_n is {measured_n_values} for all of them -- i.e. every play "
        f"was estimated from an unmeasured prior. {code_default_sum} == DEFAULT_ALPHA (="
        f"{estimator_module.DEFAULT_ALPHA}) + DEFAULT_BETA (={estimator_module.DEFAULT_BETA}) from "
        f"the code: {prior_n_matches_default}. Mean response rate = alpha/(alpha+beta) = "
        f"{estimator_module.DEFAULT_ALPHA}/{code_default_sum} = "
        f"{round(estimator_module.DEFAULT_ALPHA / code_default_sum, 4)}, matching the estimator's own "
        "module docstring ('default alpha=1, beta=19, i.e. 5% with a pseudo-count of 20'). "
        "Labelled 'synthetic' here (a weak-by-construction modelling assumption, not measured and "
        "not part of the seeded tenant's business data) rather than 'seeded', since it is a code "
        "constant the tenant config does not override."
    ),
    "assertion_passed": prior_n_matches_default,
}
if not prior_n_matches_default:
    raise SystemExit(f"default prior cross-check FAILED: prior_n values seen = {prior_n_values}, expected [{code_default_sum}]")

# --------------------------------------------------------------------------------------- (f) who_pays

buyer_persona_text = "category or supply-chain head"
price_anchor_text = "share of waste avoided"
who_pays_line = None
for i, line in enumerate(decisions_text.splitlines(), start=1):
    if "buyer persona" in line and "price anchor" in line:
        who_pays_line = i
        assert buyer_persona_text in line and price_anchor_text in line, "quoted text drifted from docs/DECISIONS.md; re-check the exact wording"
        break
if who_pays_line is None:
    raise SystemExit("could not find the 'buyer persona' / 'price anchor' line in docs/DECISIONS.md")
who_pays_source = f"docs/DECISIONS.md:{who_pays_line} (Sec. 11 'Deck', Full order, item 8 'Impact')"

who_pays_entry = {
    "value": None,
    "unit": "text",
    "label": "projected",
    "source": who_pays_source,
    "note": (
        "Text-only per the task; no rupee number is stated anywhere for the price anchor, only the "
        "concept 'share of waste avoided'. Labelled 'projected' loosely (this is a stated go-to-"
        "market design decision, not measured/seeded/synthetic data) -- the closest of the four "
        "allowed labels, flagged as an approximation."
    ),
    "buyer_persona": {"text": buyer_persona_text, "source": who_pays_source},
    "price_anchor": {"text": price_anchor_text, "source": who_pays_source},
}

# --------------------------------------------------------------------------------------- Part 3 reproduction check
#
# Values below are transcribed by hand, once, directly from docs/impact_math.md Part 3
# (the "Gaps in the run" ... "Expected waste avoided" table), read verbatim in this sweep.
# Comparing them to the committed portfolio file checks whether Part 3's prose numbers still
# match the committed eval/raw/portfolio_2026-09-24.json it cites as its own source.

part3_claims = [
    ("Gaps in the run (sense_20260912_baseline_2aaad73c)", 555, totals["gaps"]),
    ("Total exposure (INR)", 1795463.92, totals["exposure_inr"]),
    ("...online sell-by breaches, count", 330, totals["by_type"]["online_sellby_breach"]["count"]),
    ("...online sell-by breaches, exposure (INR)", 1499536.95, totals["by_type"]["online_sellby_breach"]["exposure_inr"]),
    ("Planner-eligible (>= Rs 500 at stake)", 428, governor["eligible"]),
    ("Triaged out by the Cost Governor, count", 127, governor["triaged_out"]),
    ("Triaged out by the Cost Governor, exposure (INR)", 28170.54, governor["triaged_out_exposure_inr"]),
    ("Planned (valid play drafted)", 424, planned["count"]),
    ("Eligible but no valid play, count", 4, planned["eligible_no_play"]),
    ("Eligible but no valid play, exposure (INR)", 15984.64, planned["eligible_no_play_exposure_inr"]),
    ("Portfolio-wide do-nothing (write-off), INR", 1837170.32, totals["do_nothing_inr"]),
    ("Portfolio-wide blanket markdown (20%), INR", 1369538.96, totals["blanket_markdown_inr"]),
    ("Expected units moved across all 424 planned plays", 9142.64, planned["expected_units"]),
    ("Expected margin across all 424 planned plays (INR)", 347355.96, planned["expected_margin_inr"]),
    ("Expected waste avoided across all 424 planned plays (INR)", 706183.28, planned["expected_waste_avoided_inr"]),
]
part3_reproduction = []
for label, doc_value, file_value in part3_claims:
    match = abs(doc_value - file_value) < 0.005
    part3_reproduction.append({
        "row": label,
        "docs_impact_math_value": doc_value,
        "portfolio_file_value": file_value,
        "reproduced": match,
    })
not_reproduced = [r["row"] for r in part3_reproduction if not r["reproduced"]]

# --------------------------------------------------------------------------------------- assemble + write

result = {
    "_meta": {
        "generated_by": "eval/raw/docs_truth_sweep_2026-09-27/impact_numbers.py",
        "inputs": [str(p.relative_to(REPO_ROOT)) for p in (
            PORTFOLIO_PATH, COST_PATH, ESTIMATOR_PATH, PLANNER_TOOLS_PATH, TENANT_TOML_PATH,
            IMPACT_MATH_PATH, DECISIONS_PATH, GAPS_PY_PATH, FORECAST_PY_PATH,
        )],
        "sense_run_id": portfolio["sense_run_id"],
        "portfolio_as_of": portfolio["as_of"],
        "portfolio_computed_at": portfolio["computed_at"],
        "tenant_id": portfolio["tenant_id"],
    },
    "exposure": exposure_entry,
    "horizon_days": horizon_entry,
    "plays_planned": plays_planned_entry,
    "expected_margin_total": expected_margin_total_entry,
    "sales_margin": sales_margin_entry,
    "writeoff_avoided_net_of_transfer": writeoff_avoided_entry,
    "margin_sum_check": margin_sum_check_entry,
    "monthly_cost": monthly_cost_entry,
    "default_response_prior": default_response_prior_entry,
    "who_pays": who_pays_entry,
    "impact_math_part3_reproduction": {
        "rows": part3_reproduction,
        "all_reproduced": len(not_reproduced) == 0,
        "not_reproduced": not_reproduced,
        "note": (
            "docs/impact_math.md Part 3 states its totals are 'that file's own summary block' "
            "(docs/impact_math.md, sourced from eval/raw/portfolio_2026-09-24.json). Every row "
            "checked above was reproducible directly from the committed portfolio file's totals/"
            "governor/planned blocks -- none required re-running the pipeline."
        ),
    },
}

OUT_PATH.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(json.dumps(result, indent=2, ensure_ascii=False))
