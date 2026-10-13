"""jobs/sense/copy.py: templated and BigQuery-sourced copy must agree on which date counts as
"best before" and both must pass the same validator (DECISIONS §5.2 step 7, §2.5 sellby_disclosure).

Regression coverage for a real bug found running generate_copy_bigquery against a live
AI.GENERATE_TABLE call: the model was asked to state the play's online-sellby deadline_date, but
validate_copy checked for the physical expiry (`best_before`) instead, so every disclosure-
compliant BigQuery variant was silently discarded and approve() always fell back to templates.
"""
import json

import pytest

from jobs.sense import copy_pregenerated as _cp
from jobs.sense.copy import (
    _bq_prompt_text,
    generate_copy,
    normalize_rupee,
    unsupported_claim,
    validate_copy,
)

PLAY = {
    "objective": "clear_online_sellby",
    "mechanic": "bundle",
    "mechanic_params": {"bundle_price": 61},
    "target": {"deadline_type": "online_sellby", "deadline_date": "2026-09-18"},
    "audience": {"segment_ids": ["seg_1"]},
}
PRODUCT = {"name": "Masala Chips 200G"}
BEST_BEFORE = "2026-10-15"  # the physical expiry date -- deliberately different from deadline_date


def test_templated_copy_states_best_before_not_the_online_sellby_date():
    variants = generate_copy(PLAY, PRODUCT, None, BEST_BEFORE, ["en"])
    assert len(variants) == 1
    v = variants[0]
    assert v["disclosure_included"] is True
    assert "15 Oct 2026" in v["text"]
    assert "2026-09-18" not in v["text"] and "18 Sep 2026" not in v["text"]


def test_validate_copy_accepts_a_variant_that_states_best_before_in_iso_form():
    # A live model told to "state the date plainly" reliably writes the ISO string it was given
    # rather than reformatting it -- the validator must accept that form too, not just "%d %b %Y".
    variant = {"segment_id": "seg_1", "language": "en", "text": f"Bundle for Rs 61. Best before: {BEST_BEFORE}.", "disclosure_included": True}
    accepted, reasons = validate_copy([variant], PLAY, BEST_BEFORE)
    assert accepted == [{**variant, "text": f"Bundle for ₹61. Best before: {BEST_BEFORE}."}] and reasons == []


def test_validate_copy_rejects_a_variant_stating_the_wrong_date():
    # This is exactly the bug found live: copy correctly states the play's online-sellby
    # deadline_date instead of the physical best_before -- must be rejected, not silently accepted,
    # since a customer-facing "best before" line must never show the wrong date.
    variant = {"segment_id": "seg_1", "language": "en", "text": "Bundle for Rs 61. Best before: 2026-09-18.", "disclosure_included": False}
    accepted, reasons = validate_copy([variant], PLAY, BEST_BEFORE)
    assert accepted == [] and reasons and "best-before" in reasons[0]


def test_validate_copy_requires_disclosure_only_for_near_deadline_objectives():
    non_deadline_play = {**PLAY, "objective": "revive_slow_mover"}
    variant = {"segment_id": "seg_1", "language": "en", "text": "Try this again this week!", "disclosure_included": False}
    accepted, reasons = validate_copy([variant], non_deadline_play, BEST_BEFORE)
    assert accepted == [variant] and reasons == []


def test_templated_variants_are_distinct_for_the_seeded_tea_and_chips_plays(base_store):
    """Row 1.3: the Copy tab showed one sentence once per segment. Each segment now gets its own
    phrasing of the same offer, with the same facts, and every line still passes the validator."""
    import json

    from agents.gate.store import load_catalogue

    catalogue = load_catalogue(base_store)
    for play_id in ("play_tea_ds04_v1", "play_chips_ds07_v1"):
        play = json.loads(base_store.find("plays", play_id=play_id)[-1]["play_json"])
        gap = base_store.find("gaps", gap_id=play["gap_id"])[-1]
        best_before = gap["evidence"].get("expiry_date")
        params = play.get("mechanic_params") or {}
        partner = catalogue.get(params.get("bundle_sku") or "")
        variants = generate_copy(play, catalogue[play["target"]["sku"]], partner, best_before, play["copy"]["language_set"])
        texts = [v["text"] for v in variants]
        assert len(texts) == len(play["audience"]["segment_ids"]) >= 5
        assert len(set(texts)) == len(texts), texts
        accepted, reasons = validate_copy(variants, play, best_before)
        assert len(accepted) == len(variants) and reasons == []
        assert all(v["disclosure_included"] for v in variants)
        if "bundle_price" in params:
            assert all(f"₹{params['bundle_price']:g}" in t for t in texts)


def test_every_phrasing_keeps_its_facts_and_languages_stay_in_step():
    from jobs.sense.copy import TEMPLATES

    needs = {"bundle": ["{name}", "{partner}", "{bundle_price}", "{best_before}"], "coupon": ["{name}", "{discount_pct}", "{best_before}"],
             "outlet_markdown": ["{name}", "{markdown_pct}", "{best_before}"], "transfer_plus_nudge": ["{name}", "{best_before}"], "preorder": ["{name}", "{eta}"]}
    for lang, by_mech in TEMPLATES.items():
        for mech, slots in needs.items():
            tpls = by_mech[mech] if isinstance(by_mech[mech], list) else [by_mech[mech]]
            assert len(set(tpls)) == len(tpls) >= 5
            for t in tpls:
                assert all(sl in t for sl in slots), (lang, mech, t)


# --- claims the offer does not make: rejected by the runtime validator, English and Kannada ---------


def _variant(text, lang="en"):
    return {"segment_id": "seg_1", "language": lang, "text": text, "disclosure_included": True}


@pytest.mark.parametrize("text", [
    "Freshly stocked for today! Best before 15 Oct 2026.",
    "Just arrived and perfectly fresh. Best before 15 Oct 2026.",
    "Fresh stock for your weekly shop. Best before 15 Oct 2026.",
    "ತಾಜಾ ಸ್ಟಾಕ್ ಈಗ ಲಭ್ಯ. ಬಳಕೆಗೆ ಉತ್ತಮ 15 Oct 2026.",
    "ಈಗಷ್ಟೇ ಬಂದಿದೆ. ಬಳಕೆಗೆ ಉತ್ತಮ 15 Oct 2026.",
])
def test_freshness_claims_are_rejected_for_every_mechanic_but_preorder(text):
    for mechanic in ("bundle", "outlet_markdown", "coupon", "transfer_plus_nudge"):
        play = {**PLAY, "mechanic": mechanic}
        lang = "kn" if any("ಀ" <= c <= "೿" for c in text) else "en"
        accepted, reasons = validate_copy([_variant(text, lang)], play, BEST_BEFORE)
        assert accepted == [] and any("does not make" in r for r in reasons), (mechanic, text)
    assert unsupported_claim(text, "preorder") is None  # stock arriving soon may be called fresh


@pytest.mark.parametrize("text", [
    "Your Darjeeling Tea 100G is waiting in your cart. Best before 15 Oct 2026.",
    "Complete your order now. Best before 15 Oct 2026.",
    "Your reservation is confirmed. Best before 15 Oct 2026.",
    "Reserved for you at the outlet. Best before 15 Oct 2026.",
    "We saved a pack for you. Best before 15 Oct 2026.",
    "Limited time only. Best before 15 Oct 2026.",
    "Today only! Best before 15 Oct 2026.",
    "Last chance to pick it up. Best before 15 Oct 2026.",
    "A new arrival at your store. Best before 15 Oct 2026.",
    "Freshly made and ready. Best before 15 Oct 2026.",
    "Enjoy it at its freshest. Best before 15 Oct 2026.",
    "Just in time for the weekend. Best before 15 Oct 2026.",
    "ನಿಮ್ಮ ಕಾರ್ಟ್‌ನಲ್ಲಿ ಕಾಯುತ್ತಿದೆ. ಬಳಕೆಗೆ ಉತ್ತಮ 15 Oct 2026.",
])
def test_unsupported_claims_are_rejected_for_every_mechanic(text):
    for mechanic in ("bundle", "outlet_markdown", "coupon", "transfer_plus_nudge", "preorder"):
        play = {**PLAY, "mechanic": mechanic}
        lang = "kn" if any("ಀ" <= c <= "೿" for c in text) else "en"
        accepted, reasons = validate_copy([_variant(text, lang)], play, BEST_BEFORE)
        assert accepted == [] and any("does not make" in r for r in reasons), (mechanic, text)


def test_supported_wording_is_not_rejected():
    ok, reasons = validate_copy([_variant("Masala Chips 200G with Cola Classic 250ML for Rs 61. Best before 15 Oct 2026."),
                                 _variant("Add Masala Chips 200G to your usual order this week. Best before 15 Oct 2026.")], PLAY, BEST_BEFORE)
    assert len(ok) == 2 and reasons == []


def test_templated_copy_never_makes_those_claims():
    for mechanic in ("bundle", "outlet_markdown", "coupon", "transfer_plus_nudge", "preorder"):
        play = {**PLAY, "mechanic": mechanic, "mechanic_params": {"bundle_price": 61, "discount_pct": 10, "markdown_pct": 10}}
        for v in generate_copy(play, PRODUCT, {"name": "Cola Classic 250ML"}, BEST_BEFORE, ["en", "kn"]):
            assert unsupported_claim(v["text"], mechanic) is None, (mechanic, v["text"])


def test_prompt_angle_has_no_freshness_wording_and_the_prompt_forbids_the_claims():
    from jobs.sense.copy import SEGMENT_ANGLES

    assert not any("fresh" in a.lower() for a in SEGMENT_ANGLES)
    p = _bq_prompt_text("Darjeeling Tea 100G", "transfer_plus_nudge", None, None, "2026-11-20", "en", SEGMENT_ANGLES[1])
    assert "never mention a cart or an order" in p and "Do not call the stock fresh or newly arrived" in p
    assert "newly arrived" not in _bq_prompt_text("Cola Zero 500ML", "preorder", None, None, None, "en")


def test_committed_pregenerated_copy_makes_none_of_those_claims(base_store):
    """Over the committed fixture: no non-preorder variant says fresh/just arrived (EN or KN), and
    no variant of any play mentions a cart, an order or a reservation it does not make."""
    _cp.clear_cache()
    fixture = _cp.load_fixture(_cp.FIXTURE_PATH)
    assert fixture
    for play_id, entry in fixture.items():
        mechanic = json.loads(base_store.find("plays", play_id=play_id)[-1]["play_json"])["mechanic"]
        for v in entry["variants"]:
            assert unsupported_claim(v["text"], mechanic) is None, (play_id, v["segment_id"], v["language"], v["text"])
            if mechanic != "preorder":
                low = v["text"].lower()
                assert not any(w in low for w in ("fresh", "just arrived")) and "ತಾಜಾ" not in v["text"] and "ಈಗಷ್ಟೇ" not in v["text"]


@pytest.mark.parametrize("text,expected", [
    ("Chips for Rs 50 today", "Chips for ₹50 today"),
    ("Chips for Rs. 50 today", "Chips for ₹50 today"),
    ("Chips for Rs.50 today", "Chips for ₹50 today"),
    ("Chips for ₹50 today", "Chips for ₹50 today"),
    ("Chips with no price, best before 2026-10-15", "Chips with no price, best before 2026-10-15"),
    ("Rs 50 and Rs. 61.50", "₹50 and ₹61.50"),
    ("Doors and Rsvp 5", "Doors and Rsvp 5"),
])
def test_normalize_rupee(text, expected):
    assert normalize_rupee(text) == expected


def test_validate_copy_renders_rupee_sign_without_mutating_input():
    original = _variant("Masala Chips 200G with Cola Classic 250ML for Rs 61. Best before 15 Oct 2026.")
    snapshot = dict(original)
    ok, reasons = validate_copy([original], PLAY, BEST_BEFORE)
    assert reasons == [] and ok[0]["text"] == "Masala Chips 200G with Cola Classic 250ML for ₹61. Best before 15 Oct 2026."
    assert original == snapshot and ok[0] is not original
