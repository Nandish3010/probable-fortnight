"""services.feedback.summary and harness/feedback_summary.py.

No fixture here is, or pretends to be, a real response: every row is `source: "test"`. The
aggregation arithmetic is exercised through `aggregate()`, which takes already-filtered rows;
`summarize()` and the harness command -- the only paths that produce numbers anyone quotes --
are tested to drop every one of these rows.
"""
from __future__ import annotations

import json
import re

import pytest

from services.feedback import summary as S
from services.feedback.intake import form
from services.feedback.store import LocalFeedbackStore

FORM = form()


def _row(i, mode="self", source="test", **answers):
    a = {"a1_role": "store_manager", "a2_business": "kirana", "e4_consent": True, **answers}
    return {"response_id": f"{i:032x}", "submitted_at": "2026-09-26T10:00:00Z", "form_version": FORM["form_version"], "mode": mode, "source": source, "answers": a, "has_contact": False}


def test_summarize_excludes_test_rows(monkeypatch):
    seen = {}
    real_aggregate = S.aggregate

    def spy(rows, *a, **k):
        seen["rows"] = rows
        return real_aggregate(rows, *a, **k)

    monkeypatch.setattr(S, "aggregate", spy)
    out = S.summarize([_row(1), _row(2, b1_frequency="daily"), _row(3, source="")], FORM, "2026-09-26T00:00:00Z")
    assert seen["rows"] == []
    assert out["responses"] == {"total": 0, "self": 0, "interview": 0} and out["excluded_non_real"] == 3
    assert all(o["count"]["total"] == 0 for o in out["questions"]["b1_frequency"]["options"])


def test_harness_command_excludes_test_rows(tmp_path, monkeypatch):
    fb = tmp_path / "fb"
    store = LocalFeedbackStore(fb)
    for i in range(10):
        store.add(_row(i, d1_biggest_pain=f"test-only text {i}", e2_quote_ok="yes"), {"response_id": f"{i:032x}", "reach": "t@example.invalid"})
    monkeypatch.setenv("TAAL_FEEDBACK_STORE", "local")
    monkeypatch.setenv("TAAL_FEEDBACK_DIR", str(fb))
    from harness import feedback_summary

    assert feedback_summary.main(["--out-dir", str(tmp_path / "out")]) == 0
    [js] = list((tmp_path / "out").glob("feedback_summary_*/summary.json"))
    [md] = list((tmp_path / "out").glob("feedback_summary_*/summary.md"))
    s = json.loads(js.read_text())
    assert s["responses"]["total"] == 0 and s["excluded_non_real"] == 10 and s["quotes"] == []
    for text in (js.read_text(), md.read_text()):
        assert "test-only text" not in text and "t@example.invalid" not in text and "0" * 31 not in text


def test_counts_not_percentages_below_eight():
    rows = [_row(i, b1_frequency="weekly") for i in range(7)]
    q = S.aggregate(rows, FORM, "t")["questions"]["b1_frequency"]
    weekly = next(o for o in q["options"] if o["value"] == "weekly")
    assert weekly["count"]["total"] == 7 and weekly["pct"]["total"] is None


def test_percentages_at_eight_and_split_by_mode():
    rows = [_row(i, b1_frequency="weekly") for i in range(6)] + [_row(10 + i, mode="interview", b1_frequency="daily") for i in range(2)]
    q = S.aggregate(rows, FORM, "t")["questions"]["b1_frequency"]
    weekly = next(o for o in q["options"] if o["value"] == "weekly")
    assert weekly["count"] == {"total": 6, "self": 6, "interview": 0}
    assert weekly["pct"]["total"] == 75.0
    assert weekly["pct"]["self"] is None and weekly["pct"]["interview"] is None, "each mode has its own base below 8"


def test_multi_select_counts_respondents_and_skipped_section_is_not_answered():
    rows = [_row(i, c0_seen_demo="yes_live", c2_most_valuable=["human_approval", "holdout_measurement"]) for i in range(8)] + [_row(20, c0_seen_demo="no")]
    s = S.aggregate(rows, FORM, "t")
    c2 = s["questions"]["c2_most_valuable"]
    assert c2["shown"]["total"] == 8 and c2["answered"]["total"] == 8
    assert {o["value"]: o["pct"]["total"] for o in c2["options"]}["human_approval"] == 100.0


def test_scale_median_only_from_eight():
    rows = [_row(i, c0_seen_demo="yes_live", c1_usefulness=v) for i, v in enumerate([1, 2, 3, 4, 4, 5, 5])]
    assert S.aggregate(rows, FORM, "t")["questions"]["c1_usefulness"]["median"] is None
    rows.append(_row(99, c0_seen_demo="yes_live", c1_usefulness=5))
    assert S.aggregate(rows, FORM, "t")["questions"]["c1_usefulness"]["median"] == 4.0


def test_crosstabs_by_role_and_business():
    rows = [_row(1, b5_fssai="no"), _row(2, a1_role="owner", a2_business="quick_commerce", b5_fssai="yes_limits")]
    ct = S.aggregate(rows, FORM, "t")["crosstabs"]
    assert [g["value"] for g in ct["a1_role"]] == ["store_manager", "owner"]
    owner = next(g for g in ct["a1_role"] if g["value"] == "owner")
    fssai = {o["value"]: o["count"]["total"] for o in owner["questions"]["b5_fssai"]["options"]}
    assert fssai["yes_limits"] == 1 and fssai["no"] == 0
    assert [g["value"] for g in ct["a2_business"]] == ["kirana", "quick_commerce"]


@pytest.mark.parametrize("quote_ok,expected", [("yes", 1), ("no", 0), (None, 0)])
def test_quotes_only_with_permission_verbatim_and_role_only(quote_ok, expected):
    extra = {"e2_quote_ok": quote_ok} if quote_ok else {}
    rows = [_row(1, d1_biggest_pain="  Verbatim, with odd spacing.  ", **extra)]
    quotes = S.aggregate(rows, FORM, "t")["quotes"]
    assert len(quotes) == expected
    if quotes:
        assert quotes[0] == {"question": "d1_biggest_pain", "text": "  Verbatim, with odd spacing.  ", "role": "Store or dark-store manager", "business": "Kirana or independent store", "mode": "self"}


def test_markdown_reports_mode_on_every_count():
    md = S.render_markdown(S.aggregate([_row(1, b1_frequency="daily")], FORM, "2026-09-26T00:00:00Z"))
    assert "Daily | 1 · self 1 · interview 0 |" in md
    assert not re.search(r"\(\d+(\.\d)?%\)", md), "no percentage below the minimum base"


# ----------------------------------------------------------------------------- owner exclusions


def test_substantive_answers_skip_about_you_routing_consent_and_non_answers():
    thin = _row(1, a3_scale="2_10", a4_online_food="yes", c0_seen_demo="no", b2_writeoff_share="dont_know", b3_writeoff_value="prefer_not", d1_biggest_pain="   ", b4_current_actions=[], e1_pilot="yes", e2_quote_ok="yes")
    assert S.substantive_answers(thin["answers"], FORM) == 0
    ok = _row(2, b1_frequency="weekly", b6_measurement="control_group", d1_biggest_pain="Late pallets.")
    assert S.substantive_answers(ok["answers"], FORM) == 3


def test_drop_reason_flags_listed_ids_first_then_thin_rows():
    flagged, thin, kept = _row(1, b1_frequency="weekly", b5_fssai="no", b6_measurement="judgement"), _row(2, b1_frequency="daily"), _row(3, b1_frequency="daily", b5_fssai="no", b6_measurement="judgement")
    ids = {flagged["response_id"]}
    assert [S.drop_reason(r, FORM, ids, 3) for r in (flagged, thin, kept)] == ["flagged", "below_min_substantive", None]


def test_exclusions_and_summarize_never_touch_non_real_rows():
    rows = [_row(1, b1_frequency="daily")]
    assert S.exclusions(rows, FORM, {rows[0]["response_id"]}, 3) == {"flagged": [], "below_min_substantive": []}
    s = S.summarize(rows, FORM, "t", exclude_ids={rows[0]["response_id"]}, min_substantive=3, counts_only=True)
    assert s["excluded_by_reason"] == {"non_real": 1, "flagged_by_owner": 0, "below_min_substantive": 0} and s["excluded_non_real"] == 1


def test_counts_only_suppresses_percentages_and_medians_at_any_base():
    rows = [_row(i, b1_frequency="weekly", c0_seen_demo="yes_live", c1_usefulness=4) for i in range(12)]
    s = S.aggregate(rows, FORM, "t", min_n=float("inf"))
    weekly = next(o for o in s["questions"]["b1_frequency"]["options"] if o["value"] == "weekly")
    assert weekly["count"]["total"] == 12 and set(weekly["pct"].values()) == {None}
    assert s["questions"]["c1_usefulness"]["median"] is None
    md = S.render_markdown({**s, "counts_only": True})
    assert not re.search(r"\(\d+(\.\d)?%\)", md) and "Counts only" in md


def test_quotes_only_from_cleared_role_and_business_pairs():
    rows = [
        _row(1, a1_role="category", a2_business="quick_commerce", e2_quote_ok="yes", d1_biggest_pain="cleared category text"),
        _row(2, a1_role="store_manager", a2_business="quick_commerce", e2_quote_ok="yes", d1_biggest_pain="cleared store text"),
        _row(3, a1_role="owner", a2_business="quick_commerce", e2_quote_ok="yes", d1_biggest_pain="not cleared"),
        _row(4, a1_role="category", a2_business="kirana", e2_quote_ok="yes", d1_biggest_pain="not cleared either"),
    ]
    quotes = S.aggregate(rows, FORM, "t", quote_from=[("category", "quick_commerce"), ("store_manager", "quick_commerce")])["quotes"]
    assert sorted(q["text"] for q in quotes) == ["cleared category text", "cleared store text"]


def test_committed_exclusion_config_loads_and_forces_counts():
    kw = S.exclusion_config()
    assert len(kw["exclude_ids"]) == 3 and all(re.fullmatch(r"[0-9a-f]{32}", i) for i in kw["exclude_ids"])
    assert kw["min_substantive"] == 3 and kw["counts_only"] is True
    assert set(kw["quote_from"]) == {("category", "quick_commerce"), ("store_manager", "quick_commerce")}


def test_export_loader_drops_contact_fields(tmp_path):
    from harness.feedback_summary import load_export

    p = tmp_path / "export.jsonl"
    p.write_text(json.dumps({**_row(1), "reach": "t@example.invalid", "answers": {**_row(1)["answers"], "e3_contact": {"reach": "t@example.invalid"}}}) + "\n")
    [rec] = load_export(p)
    assert "t@example.invalid" not in json.dumps(rec) and set(rec) == {"response_id", "submitted_at", "form_version", "mode", "source", "answers"}
