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

from typing import Any

MIN_N = 8
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


def _pct(count: dict[str, int], denom: dict[str, int]) -> dict[str, float | None]:
    return {k: (round(100.0 * count[k] / denom[k], 1) if denom[k] >= MIN_N else None) for k in count}


def _shown(q: dict[str, Any], answers: dict[str, Any]) -> bool:
    cond = q.get("show_if")
    return not cond or answers.get(cond["question"]) in cond["in"]


def question_summary(rows: list[dict[str, Any]], q: dict[str, Any]) -> dict[str, Any]:
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
            opts.append({"value": value, "label": label, "count": c, "pct": _pct(c, answered)})
        out["options"] = opts
    if q["type"] == "scale":
        vals = sorted(r["answers"][qid] for r in answered_rows)
        out["median"] = (vals[(len(vals) - 1) // 2] + vals[len(vals) // 2]) / 2 if len(vals) >= MIN_N else None
    return out


def _label(q: dict[str, Any], value: str) -> str:
    return next((o["label"] for o in q.get("options", []) if o["value"] == value), value)


def summarize(records: list[dict[str, Any]], form: dict[str, Any], generated_at: str) -> dict[str, Any]:
    """The only entry point the harness command and the API call: real rows only."""
    real = [r for r in records if r.get("source") == "real"]
    return aggregate(real, form, generated_at, excluded=len(records) - len(real))


def aggregate(real: list[dict[str, Any]], form: dict[str, Any], generated_at: str, excluded: int = 0) -> dict[str, Any]:
    """Pure aggregation over rows the caller has already filtered. Unit tests call this directly
    on `source: "test"` rows so that no fixture ever has to pretend to be real."""
    qs = questions(form)
    versions: dict[str, dict[str, int]] = {}
    for v in sorted({r["form_version"] for r in real}):
        versions[v] = _split(real, lambda r, v=v: r["form_version"] == v)
    per_question = {qid: question_summary(real, q) for qid, q in qs.items() if q["type"] in (*COUNTED_TYPES, "text")}
    crosstabs: dict[str, Any] = {}
    for by in BREAKDOWNS:
        groups = []
        for value, label in _options(qs[by]):
            rows = [r for r in real if r["answers"].get(by) == value]
            if not rows:
                continue
            groups.append({
                "value": value, "label": label, "n": _split(rows, lambda r: True),
                "questions": {qid: question_summary(rows, qs[qid]) for qid in CROSSTAB_QUESTIONS},
            })
        crosstabs[by] = groups
    quotes = []
    for r in real:
        a = r["answers"]
        if a.get("e2_quote_ok") != "yes":
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
        f"({s['excluded_non_real']} test or non-real row(s) excluded).",
        "",
        f"Every cell reads `all · self · interview`: *self* means the practitioner filled the form in alone, "
        f"*interview* means a team member filled it in during a call. A percentage appears only where its own "
        f"base is at least {s['min_n_for_percentages']}; below that the cell is a count.",
        "",
        f"**Responses:** {_cell(n)}",
        "",
    ]
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
            lines += [f"Median: {q['median'] if q['median'] is not None else 'not shown (fewer than ' + str(s['min_n_for_percentages']) + ' answers)'}", ""]
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
