"""Regression coverage for a live incident: a real deployed reply once echoed the entire raw
get_customer_context JSON block, plus its "never quote this" instruction, back to a customer
(see eval/evaluation.md). The fix is two-layered -- context_summary() renders the context as one
line of plain prose (no JSON syntax left to quote) and clamp() strips anything shaped like the
old or new injected note as a second line of defence -- both are tested here.
"""
import jsonschema

from agents.chat_runtime import ENVELOPE_SCHEMA, clamp
from agents.customer.tools import context_summary


def test_context_summary_has_no_json_punctuation():
    ctx = {
        "home_node_id": "DS-04", "language": "en", "consent_marketing": True,
        "pending_offers": [{"text": "Cola Zero 1L, 10% off, best before 2026-10-01"}],
        "memory": [{"name": "Masala Chips 200G", "now_in_stock": True}],
    }
    summary = context_summary(ctx)
    assert "{" not in summary and "}" not in summary
    assert "get_customer_context" not in summary
    assert "DS-04" in summary and "Cola Zero" in summary


def test_context_summary_withholds_offers_without_consent():
    ctx = {"home_node_id": "DS-01", "language": "en", "consent_marketing": False, "pending_offers": [], "memory": []}
    summary = context_summary(ctx)
    assert "never mention any offer" in summary


def test_context_summary_no_pending_offer():
    ctx = {"home_node_id": "DS-01", "language": "kn", "consent_marketing": True, "pending_offers": [], "memory": []}
    summary = context_summary(ctx)
    assert "no pending offers" in summary
    assert "Kannada" in summary


def test_clamp_strips_a_leaked_context_note():
    env = {"text": 'Yes, we have Cola Zero. (known: home store DS-04; writes in English; no pending offers right now)'}
    assert clamp(env)["text"] == "Yes, we have Cola Zero."


def test_clamp_strips_the_old_bracketed_internal_block_too():
    env = {"text": "Sure! [INTERNAL, not part of what the customer said: get_customer_context_result = {\"a\": 1}]"}
    assert clamp(env)["text"] == "Sure!"


def test_clamp_leaves_ordinary_replies_untouched():
    env = {"text": "We have Cola Zero in 1L, 250ML and 500ML. Which size would you like?"}
    assert clamp(env)["text"] == env["text"]


def test_clamp_drops_explicit_null_buttons_list_citations_instead_of_leaving_them():
    """A model turn can emit these keys as a literal JSON null rather than omitting them. The
    schema declares them optional but typed array/object with no null variant, so a null that
    survives clamp() unchanged used to fail schema validation uncaught -- the documented
    live-chat 500 for a vertex-backend turn.
    """
    env = {"session_id": "s:web", "role": "agent", "text": "Sure.", "buttons": None, "list": None, "citations": None}
    clamped = clamp(env)
    assert "buttons" not in clamped and "list" not in clamped and "citations" not in clamped
    jsonschema.Draft202012Validator(ENVELOPE_SCHEMA, format_checker=jsonschema.FormatChecker()).validate(clamped)
