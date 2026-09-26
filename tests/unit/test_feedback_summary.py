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
    [js] = list((tmp_path / "out").glob("feedback_summary_*.json"))
    [md] = list((tmp_path / "out").glob("feedback_summary_*.md"))
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
