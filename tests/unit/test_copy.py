"""jobs/sense/copy.py: templated and BigQuery-sourced copy must agree on which date counts as
"best before" and both must pass the same validator (DECISIONS §5.2 step 7, §2.5 sellby_disclosure).

Regression coverage for a real bug found running generate_copy_bigquery against a live
AI.GENERATE_TABLE call: the model was asked to state the play's online-sellby deadline_date, but
validate_copy checked for the physical expiry (`best_before`) instead, so every disclosure-
compliant BigQuery variant was silently discarded and approve() always fell back to templates.
"""
from jobs.sense.copy import generate_copy, validate_copy

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
    assert accepted == [variant] and reasons == []


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
