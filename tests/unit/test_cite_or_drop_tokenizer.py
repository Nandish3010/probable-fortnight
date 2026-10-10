"""cite_or_drop: the number tokenizer and the citable-value set.

History: the tokenizer refused any number preceded by "-" (to skip identifiers like DS-07), which
also refused the "161" of "-161.52"; the scan resumed after the "." and reported the fraction "52"
as an uncited number. On the 28 Sep 2026 flagship recording that rejected three attempts with
"uncited numbers in rationale: 52" although no 52 appears in any of them. The rule also never
looked at `alternatives`, where the real figure (the rejected transfer's -161.52) lives. Both are
fixed; these tests pin the rules down.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from agents.gate import guardrails as gr
from agents.gate.estimator import Product

ROOT = Path(__file__).resolve().parents[2]
RECORDINGS = ROOT / "eval" / "raw" / "planner_real_traces_2026-09-28"
CHIPS = Product("SKU-MASALA-CHIPS-200G", "snacks", 25.0, 30.0, 8.0)
# the tokenizer as it was before the fix, kept only to show the root cause
LEGACY_NUMBER = re.compile(r"(?<![A-Za-z0-9_-])(\d{1,3}(?:,\d{3})+|\d+)(\.\d+)?")


def _draft(**over):
    d = {
        "objective": "clear_online_sellby", "mechanic": "coupon", "mechanic_params": {"discount_pct": 5},
        "target": {"sku": "SKU-MASALA-CHIPS-200G", "node_ids": ["DS-07"], "deadline_type": "online_sellby"},
        "audience": {"segment_ids": ["seg_1"], "purpose": "marketing", "size_before_consent": 100, "size_after_consent": 80},
        "channel": "web_chat", "copy": {"copy_status": "pending", "variants": []},
        "holdout": {"fraction": 0.1, "seed": "seed-x", "min_treated_n": 20},
        "rationale": "", "citations": [{"type": "gap", "ref": "gap_x"}],
        "expected_outcome": {"units": 4.0, "margin_inr": 20.0},
    }
    d.update(over)
    return d


def _ctx(**kw) -> gr.GuardrailContext:
    return gr.GuardrailContext(product=CHIPS, **kw)


def _cite(rationale: str, **fields) -> dict:
    return gr.rule_cite_or_drop(_draft(rationale=rationale, **fields), _ctx())


# --------------------------------------------------------------------------- tokenizer table

CASES = [
    # sign
    ("neg_decimal_percent", "Net margin -161.52 against a floor of 8.00%", [-161.52, 8.0]),
    ("neg_decimal_inr_suffix", "a negative expected margin of -161.52 INR.", [-161.52]),
    ("unicode_minus", "margin of −161.52", [-161.52]),
    ("minus_before_rupee_sign", "margin of -₹161.52", [-161.52]),
    ("minus_after_rupee_sign", "margin of ₹-161.52", [-161.52]),
    ("minus_after_inr_word", "margin of INR -161.52", [-161.52]),
    ("minus_after_rs_dot", "margin of Rs.-161.52", [-161.52]),
    ("negative_small_integer_is_a_claim", "a swing of -5 units", [-5.0]),
    ("negative_in_parens", "margin (-7516.95 INR) is unviable", [-7516.95]),
    ("range_both_ends", "between 20-30 units", [20.0, 30.0]),
    ("range_with_percent", "an uplift of 30-40%", [30.0, 40.0]),
    ("range_en_dash", "an uplift of 30–40%", [30.0, 40.0]),
    ("spaced_dash_is_not_a_sign", "stock - 52 units left", [52.0]),
    ("bullet_dash_is_not_a_sign", "- 52 units", [52.0]),
    ("hyphen_glued_to_a_word_is_not_a_sign", "margin-161.52", [161.52]),
    # decimals and counts
    ("two_decimals", "22.98 units and 191.88 INR", [22.98, 191.88]),
    ("trailing_zero_decimal", "floor of 8.00%", [8.0]),
    ("leading_dot_decimal", "about .5 of them", [0.5]),
    ("sentence_final_period", "cleared 58. Next 12 units", [58.0, 12.0]),
    ("single_digit_integers_are_counts", "3 segments, 7 days, 9.5 days", [9.5]),
    ("single_digit_decimal_is_a_claim", "5.0 units", [5.0]),
    # grouping
    ("western_grouping", "₹1,795,464 at stake", [1795464.0]),
    ("indian_grouping", "₹17,95,464 at stake", [1795464.0]),
    ("indian_grouping_with_decimals", "₹17,95,463.92", [1795463.92]),
    ("four_digit_grouping", "₹9,200", [9200.0]),
    ("flat_digits", "9200 units", [9200.0]),
    ("comma_list_is_not_grouping", "segments 20,30,40", [20.0, 30.0, 40.0]),
    ("comma_space_list", "tiers 20, 30 and 40", [20.0, 30.0, 40.0]),
    # currency, percent, units
    ("currency_forms", "₹58.50, Rs 58.50, Rs.58.50, INR 58.50, INR58.50, 58.50 INR", [58.5] * 6),
    ("percent_and_ci", "95% CI and 14.27% margin", [95.0, 14.27]),
    ("pack_size_letters", "Masala Chips 200G and Orange Juice 500ML", [200.0, 500.0]),
    ("magnitude_words_are_not_interpreted", "₹1.2 lakh, 3 crore, 50k, ₹1.8M", [1.2, 50.0, 1.8]),
    # dates
    ("iso_date", "sell-by on 2026-09-18", []),
    ("iso_timestamps", "window 2026-09-12T00:00:00Z to 2026-09-18T23:59:59Z", []),
    ("text_date_day_first", "by 18 Sept 2026", []),
    ("text_date_month_first", "since Sept 18, 2026", []),
    ("text_date_ordinal", "on the 18th of September 2026", []),
    ("month_and_year", "in September 2026", []),
    ("slash_date", "due 18/09/2026", []),
    ("date_beside_a_real_figure", "on 18 Sept 2026 we clear 368 units", [368.0]),
    # identifiers
    ("identifiers", "Lot B-CHIPS-DS07-01 at DS-07 via OUT-03, SKU-MASALA-CHIPS-200G, seg_5, run_04, play_chips_ds07_v1, est-v1, v1, p50, DS07", []),
    ("identifier_beside_a_real_figure", "368 units of SKU-MASALA-CHIPS-200G at DS-07", [368.0]),
    ("word_glued_digits", "version v12, node DS12 and the p95 latency", []),
    ("decimal_glued_to_a_word_leaves_no_fragment", "p161.52 and v1.52", []),
    ("empty", "", []),
    ("no_digits", "Prefer bundles and transfers over markdowns.", []),
]


@pytest.mark.parametrize("text,expected", [pytest.param(t, e, id=i) for i, t, e in CASES])
def test_numbers_in_text(text, expected):
    assert gr.numbers_in_text(text) == expected


def test_legacy_regex_reproduces_the_recorded_false_positive():
    legacy = [m.group(0) for m in LEGACY_NUMBER.finditer("expected margin of -161.52 INR")]
    assert legacy == ["52"]
    assert gr.numbers_in_text("expected margin of -161.52 INR") == [-161.52]


# --------------------------------------------------------------------------- the rule

def test_reported_case_passes():
    res = _cite("Net margin -161.52 against a floor of 8.00%", expected_outcome={"margin_inr": -161.52, "floor_pct": 8.0})
    assert res["passed"], res["detail"]


def test_explicit_minus_must_match_a_negative_cited_value():
    flipped = _cite("Net margin -161.52 INR", expected_outcome={"margin_inr": 161.52})
    assert not flipped["passed"] and "-161.52" in flipped["detail"]
    assert _cite("a loss of 161.52 INR", expected_outcome={"margin_inr": -161.52})["passed"]


@pytest.mark.parametrize("field,value", [
    ("expected_outcome", {"margin_inr": 191.88}),
    ("counterfactuals", {"do_nothing_inr": 9200.0}),
    ("alternatives", [{"mechanic": "transfer_plus_nudge", "mechanic_params": {"transfer_units": 368}, "expected_units": 22.98, "expected_margin_inr": -161.52, "rejected_because": "negative expected margin"}]),
    ("target", {"sku": "SKU-MASALA-CHIPS-200G", "units": 368}),
    ("mechanic_params", {"bundle_price": 58.5}),
    ("audience", {"size_before_consent": 426, "size_after_consent": 334}),
    ("holdout", {"fraction": 0.1, "min_treated_n": 20}),
    ("guardrails", [{"rule": "margin_floor", "passed": True, "detail": "net margin 14.27% (net price 58.50, cost 50.15) vs snacks floor 8.00%"}]),
])
def test_every_play_field_that_carries_a_figure_is_citable(field, value):
    figures = {
        "expected_outcome": "191.88", "counterfactuals": "9200", "alternatives": "-161.52 and 22.98 and 368",
        "target": "368", "mechanic_params": "58.50", "audience": "426 and 334", "holdout": "10% and 20",
        "guardrails": "14.27%",
    }[field]
    assert _cite(f"figures {figures}", **{field: value})["passed"]
    assert not _cite("figures 777.77", **{field: value})["passed"]  # strict: nothing else rides along


def test_a_figure_in_no_field_still_fails_and_is_named():
    res = _cite("margin 777.77 and loss of -555.55 and 4.00 units", alternatives=[{"expected_margin_inr": -161.52}])
    assert not res["passed"] and "-555.55, 777.77" in res["detail"]


def test_range_second_end_is_checked():
    res = _cite("20-30 units", expected_outcome={"units": 20.0})
    assert not res["passed"] and res["detail"].endswith("30")


def test_dates_are_not_claims_even_when_the_play_does_not_state_them():
    assert _cite("clear by 18 Sept 2026 after 2026-09-12", expected_outcome={})["passed"]


@pytest.mark.parametrize("text,cited", [
    ("₹9,194", 9194.12), ("₹17,95,464", 1795463.92), ("₹1,795,464", 1795463.92), ("23 units", 22.98), ("8189", 8188.78),
])
def test_rounding_to_displayed_precision_matches(text, cited):
    assert _cite(f"about {text}", expected_outcome={"v": cited})["passed"]


def test_materially_different_large_figure_fails():
    res = _cite("₹17,98,000", expected_outcome={"v": 1795463.92})
    assert not res["passed"]


def test_large_uncited_figure_is_named_as_written_not_in_exponent_form():
    res = _cite("₹17,95,464 at stake", expected_outcome={})
    assert "1795464" in res["detail"] and "e+" not in res["detail"]


def test_success_detail_format_is_unchanged():
    # harness/recorded_traces.py compares this string with the one stored on a recorded play
    assert _cite("80 consented", audience={"size_after_consent": 80})["detail"] == "1 number(s) in rationale all cited; 1 citation(s) resolve"


# --------------------------------------------------------------------------- recorded runs

def _trace(run: str) -> list[dict]:
    path = RECORDINGS / run / "trace.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _attempts(run: str):
    """(attempt, recorded play with its full rationale, recorded response) per propose_play try."""
    rows = _trace(run)
    out = []
    for i, row in enumerate(rows):
        fr = row.get("function_response")
        if not (isinstance(fr, dict) and fr.get("name") == "propose_play"):
            continue
        call = rows[i - 1]
        play = json.loads(json.dumps(call["function_call"]["args"]["play"]))
        if "rationale" not in call:
            continue  # a schema-invalid attempt: never reached the guardrails
        play["rationale"] = call["rationale"]  # args copy is cut at 400 characters
        out.append((row["attempt"], play, fr["response"]))
    return out


def _resolving_ctx():
    return _ctx(resolve_citation=lambda t, r: True)  # all four recorded citations resolved live


def test_run_04_rejected_attempts_were_a_tokenizer_defect_and_now_pass():
    attempts = _attempts("run_04")
    assert [a for a, _, _ in attempts] == [1, 2, 3, 4]
    for attempt, play, response in attempts[:3]:
        assert response["errors"] == ["guardrail cite_or_drop: uncited numbers in rationale: 52"]
        assert "-161.52" in play["rationale"]
        assert not re.search(r"(?<![\d.])52(?!\d)", play["rationale"])  # no 52 anywhere in the text
        assert 52.0 not in gr.numbers_in_text(play["rationale"])
        res = gr.rule_cite_or_drop(play, _resolving_ctx())
        assert res["passed"], (attempt, res["detail"])


def test_run_04_real_reason_is_the_missing_alternatives_scan():
    # With a correct tokenizer but the old citable set, the figure that would have been named is
    # the rejected transfer's own margin -161.52.
    for _, play, _ in _attempts("run_04")[:3]:
        assert play["alternatives"][0]["expected_margin_inr"] == -161.52
        res = gr.rule_cite_or_drop({**play, "alternatives": []}, _resolving_ctx())
        assert not res["passed"] and res["detail"] == "uncited numbers in rationale: -161.52"


def test_run_04_accepted_attempt_keeps_its_single_claim():
    _, play, response = _attempts("run_04")[3]
    assert response["valid"] and gr.numbers_in_text(play["rationale"]) == [200.0]


@pytest.mark.parametrize("run", ["run_02", "run_03", "run_04"])
def test_every_recorded_cite_or_drop_rejection_in_the_flagship_recording_now_passes(run):
    seen = 0
    for _, play, response in _attempts(run):
        if any("cite_or_drop" in e for e in response["errors"]):
            seen += 1
            assert gr.rule_cite_or_drop(play, _resolving_ctx())["passed"]
    assert seen


def test_a_genuinely_invented_figure_from_an_earlier_recording_is_still_rejected():
    # planner_prompt_v6_2026-09-24, gap_7bcc0cc853: "margin of 9.744%" exists nowhere in the play;
    # 760.33 is the markdown alternative's own margin and is now recognised.
    rationale = ("This play bundles Cream 400G with Wheat Bread 400G at a price of 250 INR to clear 31.92 units, generating an "
                 "expected margin of 777.57 INR. This is preferred over a markdown play which yielded a lower expected margin of "
                 "760.33 INR. The bundle maintains a margin of 9.744%, which is above the 8% category floor.")
    play = _draft(
        rationale=rationale, mechanic_params={"bundle_sku": "SKU-WHEAT-BREAD-400G", "bundle_price": 250},
        expected_outcome={"units": 31.92, "margin_inr": 777.57}, holdout={"fraction": 0.05, "seed": "seed-x", "min_treated_n": 1},
        alternatives=[{"mechanic": "outlet_markdown", "expected_units": 31.92, "expected_margin_inr": 760.33, "rejected_because": "lower expected margin", "mechanic_params": {}}],
    )
    res = gr.rule_cite_or_drop(play, _ctx())
    assert not res["passed"] and res["detail"] == "uncited numbers in rationale: 9.744"


def _stored_plays():
    paths = sorted((ROOT / "fixtures" / "plays" / "valid").glob("*.json")) + sorted(RECORDINGS.glob("run_*/play.json"))
    for path in paths:
        play = json.loads(path.read_text(encoding="utf-8"))
        stored = next((g for g in play.get("guardrails") or [] if g["rule"] == "cite_or_drop"), None)
        if stored:
            yield pytest.param(play, stored["detail"], id=f"{path.parent.name}/{path.name}")


@pytest.mark.parametrize("play,stored_detail", list(_stored_plays()))
def test_stored_plays_reproduce_their_recorded_cite_or_drop_detail(play, stored_detail):
    # harness/recorded_traces.validate_recording rejects a recording whose recomputed guardrail
    # results differ from the stored ones, so a tokenizer change must not shift any stored count.
    assert gr.rule_cite_or_drop(play, _ctx())["detail"] == stored_detail


# --------------------------------------------------------------------------- properties

def _indian(n: int) -> str:
    s = str(n)
    if len(s) <= 3:
        return s
    head, tail = s[:-3], s[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    return ",".join([head, *groups, tail] if head else [*groups, tail])


def _render(x: float, style: str) -> str:
    sign = "-" if x < 0 else ""
    whole, frac = f"{abs(x):.2f}".split(".")
    grouped = {"plain": whole, "western": f"{int(whole):,}", "indian": _indian(int(whole))}
    body = {"plain": grouped["plain"], "western": grouped["western"], "indian": grouped["indian"]}
    return {"plain": f"{sign}{body['plain']}.{frac}", "western": f"{sign}{body['western']}.{frac}",
            "indian": f"{sign}{body['indian']}.{frac}", "rupee": f"{sign}₹{body['indian']}.{frac}",
            "inr": f"{sign}{body['plain']}.{frac} INR", "pct": f"({sign}{body['plain']}.{frac}%)"}[style]


@settings(max_examples=300, deadline=None)
@given(x=st.floats(-1e9, 1e9, allow_nan=False, allow_infinity=False), style=st.sampled_from(["plain", "western", "indian", "rupee", "inr", "pct"]))
def test_property_a_rendered_figure_is_extracted_whole_and_matched(x, style):
    rendered = _render(x, style)
    value = float(re.sub(r"[^0-9.\-]", "", rendered))  # what the text says
    assert gr.numbers_in_text(f"margin was {rendered} overall") == [value]
    assert gr._matches(value, [x])
    assert _cite(f"margin was {rendered} overall", expected_outcome={"margin_inr": x})["passed"]


@settings(max_examples=200, deadline=None)
@given(prefix=st.from_regex(r"[A-Z]{1,5}", fullmatch=True), n=st.integers(0, 99999), sep=st.sampled_from(["-", "_"]))
def test_property_identifiers_never_yield_figures(prefix, n, sep):
    assert gr.numbers_in_text(f"lot {prefix}{sep}{n:02d} and {prefix}{n}") == []


@settings(max_examples=200, deadline=None)
@given(text=st.text(max_size=200))
def test_property_tokenizer_never_raises(text):
    assert all(isinstance(v, float) for v in gr.numbers_in_text(text))
    gr.rule_cite_or_drop(_draft(rationale=text), _ctx())
