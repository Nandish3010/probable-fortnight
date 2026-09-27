"""Deterministic aggregates over real feedback responses. The only producer of the numbers the
deck quotes (via harness/feedback_summary.py) and the only thing /feedback/results shows.

Rules, each enforced here rather than left to whoever reads the output:
- only `source == "real"` rows; anything else is counted as excluded and never aggregated;
- every figure is split by `mode` (self-filled vs filled in by the team during an interview),
  because those are different grades of evidence;
- a percentage is only given where its own denominator is at least MIN_N; below that the cell
  is a count and its `pct` is None (the Measure job's "unmeasured" rule, applied to surveys);
- quotes are verbatim free text from respondents who answered e2_quote_ok = yes, attributed by
  role and business type only; no response_id, timestamp or contact detail is ever emitted.
"""
from __future__ import annotations

import json
from collections.abc import Collection
from pathlib import Path
from typing import Any

EXCLUSIONS_PATH = Path(__file__).resolve().parents[2] / "config" / "feedback_exclusions.json"

MIN_N = 8
# A "substantive" answer is one about the respondent's practice or view (sections B-D), not the
# About-you / routing / consent fields every submission carries, and not a non-answer.
SUBSTANTIVE_SECTIONS = ("B", "C", "D")
NON_SUBSTANTIVE_QUESTIONS = ("c0_seen_demo",)
NON_ANSWERS = ("dont_know", "prefer_not", "not_sure")
MODES = ("self", "interview")
BREAKDOWNS = ("a1_role", "a2_business")
CROSSTAB_QUESTIONS = ("a4_online_food", "b1_frequency", "b2_writeoff_share", "b3_writeoff_value", "b4_current_actions", "b5_fssai", "b6_measurement", "c1_usefulness", "c2_most_valuable", "c3_blockers", "c4_pay_model", "e1_pilot")
QUOTE_QUESTIONS = ("d1_biggest_pain", "d2_suggestion")
COUNTED_TYPES = ("single", "multi", "scale")


def questions(form: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {q["id"]: q for s in form["sections"] for q in s["questions"]}


def _options(q: dict[str, Any]) -> list[tuple[Any, str]]:
    if q["type"] == "scale":
        sc = q["scale"]
        out = []
        for v in range(sc["min"], sc["max"] + 1):
            label = f"{v} ({sc['min_label']})" if v == sc["min"] else f"{v} ({sc['max_label']})" if v == sc["max"] else str(v)
            out.append((v, label))
        return out
    return [(o["value"], o["label"]) for o in q["options"]]


def _split(rows: list[dict[str, Any]], pred) -> dict[str, int]:
    out = {"total": 0, **{m: 0 for m in MODES}}
    for r in rows:
        if pred(r):
            out["total"] += 1
            out[r["mode"]] += 1
    return out


def _pct(count: dict[str, int], denom: dict[str, int], min_n: float = MIN_N) -> dict[str, float | None]:
    return {k: (round(100.0 * count[k] / denom[k], 1) if denom[k] >= min_n else None) for k in count}


def _shown(q: dict[str, Any], answers: dict[str, Any]) -> bool:
    cond = q.get("show_if")
    return not cond or answers.get(cond["question"]) in cond["in"]


def question_summary(rows: list[dict[str, Any]], q: dict[str, Any], min_n: float = MIN_N) -> dict[str, Any]:
    qid = q["id"]
    shown = [r for r in rows if _shown(q, r["answers"])]
    answered_rows = [r for r in shown if qid in r["answers"]]
    answered = _split(answered_rows, lambda r: True)
    out: dict[str, Any] = {
        "id": qid, "type": q["type"], "label": q["label"],
        "shown": _split(shown, lambda r: True), "answered": answered,
        "pct_base": "respondents who answered this question" + ("; a respondent can pick several, so options can sum past 100%" if q["type"] == "multi" else ""),
    }
    if q["type"] in COUNTED_TYPES:
        opts = []
        for value, label in _options(q):
            if q["type"] == "multi":
                c = _split(answered_rows, lambda r, v=value: v in r["answers"][qid])
            else:
                c = _split(answered_rows, lambda r, v=value: r["answers"][qid] == v)
            opts.append({"value": value, "label": label, "count": c, "pct": _pct(c, answered, min_n)})
        out["options"] = opts
    if q["type"] == "scale":
        vals = sorted(r["answers"][qid] for r in answered_rows)
        out["median"] = (vals[(len(vals) - 1) // 2] + vals[len(vals) // 2]) / 2 if len(vals) >= min_n else None
    return out


def _label(q: dict[str, Any], value: str) -> str:
    return next((o["label"] for o in q.get("options", []) if o["value"] == value), value)


def substantive_answers(answers: dict[str, Any], form: dict[str, Any]) -> int:
    n = 0
    for s in form["sections"]:
        if s["id"] not in SUBSTANTIVE_SECTIONS:
            continue
        for q in s["questions"]:
            v = answers.get(q["id"])
            if q["id"] in NON_SUBSTANTIVE_QUESTIONS or v is None or v in NON_ANSWERS:
                continue
            if isinstance(v, str) and not v.strip():
                continue
            if isinstance(v, list) and not v:
                continue
            n += 1
    return n


def exclusions(records: list[dict[str, Any]], form: dict[str, Any], exclude_ids: Collection[str] = (), min_substantive: int = 0) -> dict[str, list[str]]:
    """response_ids of real rows left out, by reason. Never deletes anything: the caller just
    does not aggregate them, and they are counted in `excluded_non_real`. Ids go to the owner's
    report only, never into the summary."""
    out: dict[str, list[str]] = {"flagged": [], "below_min_substantive": []}
    for r in records:
        reason = drop_reason(r, form, exclude_ids, min_substantive) if r.get("source") == "real" else None
        if reason:
            out[reason].append(r["response_id"])
    return {k: sorted(v) for k, v in out.items()}


def drop_reason(record: dict[str, Any], form: dict[str, Any], exclude_ids: Collection[str] = (), min_substantive: int = 0) -> str | None:
    """Why the owner's rules leave this row out, whatever its source (tests call it on test rows)."""
    if record["response_id"] in exclude_ids:
        return "flagged"
    if substantive_answers(record["answers"], form) < min_substantive:
        return "below_min_substantive"
    return None


def exclusion_config(path: Path = EXCLUSIONS_PATH) -> dict[str, Any]:
    """summarize() keyword arguments from config/feedback_exclusions.json, so the committed
    summary and the admin results page apply the same exclusions."""
    ex = json.loads(Path(path).read_text(encoding="utf-8"))
    return {
        "exclude_ids": frozenset(ex["flagged_non_genuine"]["response_ids"]), "min_substantive": int(ex["min_substantive_answers"]),
        "counts_only": bool(ex["counts_only"]), "quote_from": [(q["a1_role"], q["a2_business"]) for q in ex["quote_from"]],
    }


def summarize(records: list[dict[str, Any]], form: dict[str, Any], generated_at: str, exclude_ids: Collection[str] = (), min_substantive: int = 0,
              counts_only: bool = False, quote_from: Collection[tuple[str, str]] | None = None) -> dict[str, Any]:
    """The only entry point the harness command and the API call: real rows only, minus any the
    owner excluded (exclude_ids, or fewer than min_substantive substantive answers).
    counts_only suppresses every percentage and median whatever the base; quote_from, when given,
    keeps quotes only from these (a1_role, a2_business) pairs."""
    out = exclusions(records, form, exclude_ids, min_substantive)
    dropped = set(out["flagged"]) | set(out["below_min_substantive"])
    real = [r for r in records if r.get("source") == "real" and r["response_id"] not in dropped]
    s = aggregate(real, form, generated_at, excluded=len(records) - len(real), min_n=float("inf") if counts_only else MIN_N, quote_from=quote_from)
    s["excluded_by_reason"] = {"non_real": sum(1 for r in records if r.get("source") != "real"), "flagged_by_owner": len(out["flagged"]), "below_min_substantive": len(out["below_min_substantive"])}
    s["min_substantive_answers"] = min_substantive
    s["counts_only"] = counts_only
    return s


def aggregate(real: list[dict[str, Any]], form: dict[str, Any], generated_at: str, excluded: int = 0, min_n: float = MIN_N,
              quote_from: Collection[tuple[str, str]] | None = None) -> dict[str, Any]:
    """Pure aggregation over rows the caller has already filtered. Unit tests call this directly
    on `source: "test"` rows so that no fixture ever has to pretend to be real."""
    qs = questions(form)
    versions: dict[str, dict[str, int]] = {}
    for v in sorted({r["form_version"] for r in real}):
        versions[v] = _split(real, lambda r, v=v: r["form_version"] == v)
    per_question = {qid: question_summary(real, q, min_n) for qid, q in qs.items() if q["type"] in (*COUNTED_TYPES, "text")}
    crosstabs: dict[str, Any] = {}
    for by in BREAKDOWNS:
        groups = []
        for value, label in _options(qs[by]):
            rows = [r for r in real if r["answers"].get(by) == value]
            if not rows:
                continue
            groups.append({
                "value": value, "label": label, "n": _split(rows, lambda r: True),
                "questions": {qid: question_summary(rows, qs[qid], min_n) for qid in CROSSTAB_QUESTIONS},
            })
        crosstabs[by] = groups
    quotes = []
    for r in real:
        a = r["answers"]
        if a.get("e2_quote_ok") != "yes":
            continue
        if quote_from is not None and (a.get("a1_role"), a.get("a2_business")) not in set(map(tuple, quote_from)):
            continue
        for qid in QUOTE_QUESTIONS:
            if a.get(qid):
                quotes.append({"question": qid, "text": a[qid], "role": _label(qs["a1_role"], a["a1_role"]), "business": _label(qs["a2_business"], a["a2_business"]), "mode": r["mode"]})
    quotes.sort(key=lambda x: (x["question"], x["role"], x["business"], x["text"]))
    return {
        "generated_at": generated_at,
        "current_form_version": form["form_version"],
        "min_n_for_percentages": MIN_N,
        "responses": _split(real, lambda r: True),
        "excluded_non_real": excluded,
        "form_versions": versions,
        "questions": per_question,
        "crosstabs": crosstabs,
        "quotes": quotes,
        "themes": None,
    }


# ----------------------------------------------------------------------------- markdown

def _cell(count: dict[str, int], pct: dict[str, float | None] | None = None) -> str:
    def one(k: str) -> str:
        p = pct.get(k) if pct else None
        return f"{count[k]} ({p:g}%)" if p is not None else str(count[k])
    return f"{one('total')} · self {one('self')} · interview {one('interview')}"


def render_markdown(s: dict[str, Any]) -> str:
    n = s["responses"]
    lines = [
        f"# Practitioner feedback summary ({s['generated_at'][:10]})",
        "",
        "Generated by `uv run python -m harness.feedback_summary`; do not edit by hand. Real responses only "
        f"({s['excluded_non_real']} row(s) excluded).",
        "",
        "Every cell reads `all · self · interview`: *self* means the practitioner filled the form in alone, "
        "*interview* means a team member filled it in during a call. "
        + ("Counts only: percentages and medians are suppressed for every cell, whatever its base."
           if s.get("counts_only") else
           f"A percentage appears only where its own base is at least {s['min_n_for_percentages']}; below that the cell is a count."),
        "",
        f"**Responses:** {_cell(n)}",
        "",
    ]
    if "excluded_by_reason" in s:
        e = s["excluded_by_reason"]
        lines += [f"**Excluded, never deleted:** {e['non_real']} test or non-real, {e['flagged_by_owner']} flagged by the owner as possibly "
                  f"non-genuine, {e['below_min_substantive']} with fewer than {s['min_substantive_answers']} substantive answers.", ""]
    if s["form_versions"]:
        lines += ["| Form version | Responses |", "|---|---|"]
        lines += [f"| {v} | {_cell(c)} |" for v, c in s["form_versions"].items()]
        lines.append("")
    for q in s["questions"].values():
        lines += [f"## {q['id']}: {q['label']}", "", f"Answered: {_cell(q['answered'])} (shown to {_cell(q['shown'])})", ""]
        if "options" in q:
            lines += ["| Option | Count |", "|---|---|"]
            lines += [f"| {o['label']} | {_cell(o['count'], o['pct'])} |" for o in q["options"]]
            lines.append("")
            if q["type"] == "multi":
                lines += [f"Percentages are of {q['pct_base'].split(';')[0]}; several options can be picked.", ""]
        if q["type"] == "scale":
            why = "counts only" if s.get("counts_only") else f"fewer than {s['min_n_for_percentages']} answers"
            lines += [f"Median: {q['median'] if q['median'] is not None else f'not shown ({why})'}", ""]
    for by, groups in s["crosstabs"].items():
        lines += [f"## Cross-tab by {by}", ""]
        if not groups:
            lines += ["No responses yet.", ""]
            continue
        for qid in CROSSTAB_QUESTIONS:
            q0 = groups[0]["questions"][qid]
            header = "| Option | " + " | ".join(f"{g['label']} (n {g['n']['total']})" for g in groups) + " |"
            lines += [f"### {qid}: {q0['label']}", "", header, "|---|" + "---|" * len(groups)]
            for i, o in enumerate(q0.get("options", [])):
                cells = [_cell(g["questions"][qid]["options"][i]["count"], g["questions"][qid]["options"][i]["pct"]) for g in groups]
                lines.append(f"| {o['label']} | " + " | ".join(cells) + " |")
            lines.append("")
    lines += ["## Quotes", "", "Verbatim, only from respondents who agreed to be quoted, attributed by role and business type only.", ""]
    if not s["quotes"]:
        lines += ["None yet.", ""]
    for x in s["quotes"]:
        lines += [f"> {x['text']}", ">", f"> — {x['role']}, {x['business']} ({x['question']}, {x['mode']})", ""]
    return "\n".join(lines).rstrip() + "\n"
