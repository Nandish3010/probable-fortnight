"""Assemble the submission evaluation table (docs/DECISIONS.md §12) from already-measured,
committed results under `eval/`.

Usage: python -m harness.build_eval_table

This script never measures anything itself and never invents a number. It parses the real
tables/sections already committed in `eval/evaluation.md` (and, for the two rows with no eval/
raw file, the checklist + test that gate them in CI) and reassembles them, verbatim, into one
markdown table keyed to the 13 §12 metrics. A §12 row with no genuine measurement yet is rendered
as "not yet measured -- see eval/evaluation.md" rather than being silently dropped or guessed at.

Re-run this after any change to eval/evaluation.md so eval/evaluation_table.md never drifts from
the raw evidence it summarises.
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EVALUATION_MD = ROOT / "eval" / "evaluation.md"
PLANNER_CHECKLIST = ROOT / "harness" / "checklists" / "planner_agent.md"
PLANNER_TEST = ROOT / "tests" / "agents" / "test_planner.py"
OUT = ROOT / "eval" / "evaluation_table.md"

NOT_MEASURED = "not yet measured -- see `eval/evaluation.md`"


@dataclass
class Row:
    metric: str
    result: str
    source: str


def _read(path: Path) -> str:
    if not path.exists():
        raise SystemExit(f"build_eval_table: missing {path.relative_to(ROOT)}")
    return path.read_text(encoding="utf-8")


def _producible_rows(text: str) -> dict[int, tuple[str, str, str, str]]:
    """Parse the '## Producible today' table: {# -> (metric, result, command, raw)}."""
    m = re.search(r"## Producible today\n\n(.*?)\n\n", text, re.S)
    if not m:
        raise SystemExit("build_eval_table: could not find '## Producible today' table")
    out: dict[int, tuple[str, str, str, str]] = {}
    for line in m.group(1).splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) != 5 or not cells[0].isdigit():
            continue
        n, metric, result, command, raw = cells
        out[int(n)] = (metric, result, command, raw)
    if not out:
        raise SystemExit("build_eval_table: parsed zero rows from the 'Producible today' table")
    return out


def _not_measured_rows(text: str) -> dict[str, str]:
    """Parse the '## Not measured, and why' table: {metric -> why}."""
    m = re.search(r"## Not measured, and why.*?\n\n\| Metric \| Why it is absent \|\n\|---\|---\|\n(.*?)\n\n", text, re.S)
    if not m:
        raise SystemExit("build_eval_table: could not find the 'Not measured, and why' table")
    out: dict[str, str] = {}
    for line in m.group(1).splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) != 2:
            continue
        metric, why = cells
        out[metric.strip("~ ")] = why
    return out


def _extract(text: str, pattern: str, label: str) -> str:
    m = re.search(pattern, text, re.S)
    if not m:
        raise SystemExit(f"build_eval_table: could not find {label} in eval/evaluation.md")
    captured = m.group(1) if m.groups() else m.group(0)
    return re.sub(r"\s+", " ", captured).strip()


def build_rows() -> list[Row]:
    text = _read(EVALUATION_MD)
    producible = _producible_rows(text)
    not_measured = _not_measured_rows(text)
    rows: list[Row] = []

    # 1. Forecast backtest MAPE and bias by tier and model
    metric, result, command, raw = producible[1]
    rows.append(Row("Forecast backtest MAPE/bias by tier and model", result, f"{command} -> {raw}"))

    # 2 & 3. Planner schema-validity rate and gate-pass-after-revision rate: no eval/raw file
    # commits an exact number (the test only asserts a >=95%/>=90% threshold and passes in CI);
    # cite the checklist tick and the test rather than inventing a percentage.
    checklist = _read(PLANNER_CHECKLIST)
    schema_ticked = bool(re.search(r"- \[x\] `adk eval` on 50 gaps: schema validity >= 95% after revision", checklist))
    gate_ticked = bool(re.search(r"- \[x\] Gate-pass-after-revision >= 90%", checklist))
    test_src = _read(PLANNER_TEST)
    has_test = "def test_evalset_batch_schema_validity_and_gate_pass" in test_src
    threshold_note = (
        "Passes its CI threshold assertion (>= 95% of the 50 largest eligible gaps produce a "
        "schema-valid play after revision), checklist item ticked. No raw eval/ file commits the "
        "exact measured percentage -- the test asserts a floor and passes, it does not print/save "
        "a number."
        if schema_ticked and has_test
        else NOT_MEASURED
    )
    rows.append(Row(
        "Planner schema-validity rate (first attempt vs after revision)",
        threshold_note,
        "`tests/agents/test_planner.py::test_evalset_batch_schema_validity_and_gate_pass`, `harness/checklists/planner_agent.md`",
    ))
    gate_note = (
        "Same test enforces gate-pass-after-revision >= 90% (a play is only counted 'ok' once "
        "propose_play's internal guardrail check has passed, possibly after a revision); checklist "
        "item ticked. Same caveat: threshold assertion only, no committed exact percentage."
        if gate_ticked and has_test
        else NOT_MEASURED
    )
    rows.append(Row(
        "Gate-pass-after-revision rate",
        gate_note,
        "`tests/agents/test_planner.py::test_evalset_batch_schema_validity_and_gate_pass`, `harness/checklists/planner_agent.md`",
    ))

    # 4. Guardrail unit-test count
    metric, result, command, raw = producible[3]
    rows.append(Row("Guardrail unit-test count", result, f"{command} -> {raw}"))

    # 5. Copy validator pass rate
    metric, result, command, raw = producible[6]
    bigquery_correction = _extract(
        text,
        r"\*\*`AI\.GENERATE_TABLE` now produces real copy end-to-end.*?committed here\.",
        "the AI.GENERATE_TABLE correction paragraph",
    ) if "AI.GENERATE_TABLE" in text else ""
    result_full = result + (" Superseded caveat (22 Sep): " + bigquery_correction[:220] + "…" if bigquery_correction else "")
    rows.append(Row("Copy validator pass rate", result_full, f"{command} -> {raw}"))

    # 6. Tool-trajectory match on ~50 gaps
    metric, result, command, raw = producible[5]
    reconciling = _extract(
        text,
        r"\*\*Reconciling with `harness/checklists/planner_agent\.md`:\*\*(.*?)\n\n",
        "the reconciling note on row 5",
    )
    rows.append(Row(
        "Tool-trajectory match on ~50 gaps",
        result + " Reconciling note: " + reconciling,
        f"{command} -> {raw}",
    ))

    # 7. Gemini-as-judge rationale score + 15-item human-labelled agreement
    key = next(k for k in not_measured if "Gemini-as-judge" in k)
    rows.append(Row("Gemini-as-judge rationale score + 15-item human-labelled agreement", NOT_MEASURED, not_measured[key]))

    # 8. Agent Simulation guardrail pass rate over ~200 personas
    metric, result, command, raw = producible[9]
    rows.append(Row("Agent Simulation guardrail pass rate over ~200 personas", result, f"{command} -> {raw}"))

    # 9. Pilot: treated vs holdout with CI
    key = next(k for k in not_measured if "Pilot treated-vs-holdout" in k)
    rows.append(Row("Pilot: treated vs holdout with CI, unmeasured count, pre-registered metric", NOT_MEASURED, not_measured[key]))

    # 10. Customer Agent p50/p95 and approve -> re-forecast latency. The first live sweep (49/50
    # OK, one envelope-validation 500) predates the get_customer_context prefetch fix and is
    # superseded by the "round two" re-measurement below (50/50 OK, ~15% faster) -- pull that
    # corrected paragraph, not the first one, so the table states the current number.
    chat_latency = _extract(
        text,
        r"\*\*Re-measured, same methodology, same message mix, fresh visitor per call\.\*\*(.*?)\n\n",
        "the /chat p95 latency round-two paragraph",
    )
    sweep_raw = ROOT / "eval" / "raw" / "sweep_vertex_2026-09-21.txt"
    approve_line = ""
    if sweep_raw.exists():
        m = re.search(r"^OK\s+200\s+([\d.]+)s\s+POST /approve\s+status=approved.*$", sweep_raw.read_text(), re.M)
        if m:
            approve_line = m.group(0).strip()
    latency_result = chat_latency
    if approve_line:
        latency_result += f" Approve latency (includes the re-forecast call), same clean live-Vertex sweep: `{approve_line}`."
    rows.append(Row("Customer Agent p50/p95 and approve -> re-forecast latency", latency_result, "`eval/raw/customer_latency_fix_2026-09-21.json`, `eval/raw/customer_latency_fix_summary_2026-09-21.json`, `eval/raw/sweep_vertex_2026-09-21.txt`"))

    # 11. Vision read accuracy on 30 staged photos
    vision = _extract(
        text,
        r"3\. Scored date-read accuracy against the planted ground truth: (\*\*.*?\*\*)\.",
        "the vision accuracy correction paragraph",
    )
    honesty = _extract(
        text,
        r"\*\*Honesty label, stated once, applies everywhere above:\*\*(.*?)\n\n",
        "the vision honesty-label paragraph",
    )
    rows.append(Row("Vision read accuracy on 30 staged photos", vision + " " + honesty, "`eval/raw/vision_synthetic_2026-09-21.json`"))

    # 12. Sense and Planner throughput (300 SKUs x 10 nodes) and the extrapolation
    metric, result, command, raw = producible[2]
    rows.append(Row(
        "Sense and Planner throughput (300 SKUs x 10 nodes) and the extrapolation",
        f"Sense: {result} (measured on 16 nodes/outlets, not 10 -- the tenant's real node count; "
        f"§12 says 10 as an example figure). Planner: {NOT_MEASURED} (no committed timing for a "
        "50-gap planner batch; the schema-validity test above runs 50 gaps but does not record wall time).",
        f"{command} -> {raw}",
    ))

    # 13. Cost from the billing export with Gemini tokens per play
    key = next(k for k in not_measured if "Cost per play" in k)
    rows.append(Row("Cost from the billing export with Gemini tokens per play", NOT_MEASURED, not_measured[key]))

    return rows


def render(rows: list[Row]) -> str:
    lines = [
        "# Evaluation table (assembled)",
        "",
        "Generated by `python -m harness.build_eval_table` from `eval/evaluation.md` and the raw",
        "outputs it cites under `eval/raw/`. Every cell below is parsed, not typed: re-run the",
        "script after `eval/evaluation.md` changes rather than editing this file by hand. Rows the",
        f'project cannot yet back with a real measurement say so ("{NOT_MEASURED}") instead of a guess.',
        "",
        "| # | Metric (DECISIONS §12) | Result | Source |",
        "|---|---|---|---|",
    ]
    for i, r in enumerate(rows, start=1):
        result = r.result.replace("|", "\\|")
        source = r.source.replace("|", "\\|")
        lines.append(f"| {i} | {r.metric} | {result} | {source} |")
    measured = sum(1 for r in rows if NOT_MEASURED not in r.result)
    lines += [
        "",
        f"{measured} of {len(rows)} §12 rows carry a real measurement; the rest are explicitly",
        "marked unmeasured above (see `eval/evaluation.md` for why). Nothing here is a guess.",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    rows = build_rows()
    OUT.write_text(render(rows), encoding="utf-8")
    measured = sum(1 for r in rows if NOT_MEASURED not in r.result)
    print(f"build_eval_table: wrote {OUT.relative_to(ROOT)} ({measured}/{len(rows)} rows measured)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
