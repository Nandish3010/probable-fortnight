"""English gloss under a non-English reply (agents/chat_runtime.py: clamp, resolve_gloss; the
template in agents/customer/tools.py: offer_summary_en). The model supplies `english_gloss` when it
replies in Kannada; code clamps it, drops one that states a number the reply does not, and falls
back to a template from the offer's structured fields."""
import asyncio
from datetime import UTC, datetime

import pytest

from agents.chat_runtime import GLOSS_MAX, clamp, resolve_gloss
from agents.customer.chat import reset_sessions, run_chat_async
from agents.customer.tools import offer_summary_en
from agents.gate.config import load_tenant
from services.api.approve import approve

PLAY = "play_chips_ds07_v1"
NOW = "2026-09-12T09:05:00Z"
KN = "ಒಟ್ಟು ₹58.5. ಧನ್ಯವಾದಗಳು!"


def _env(text=KN, **extra):
    return clamp({"text": text, **extra})


def test_clamp_prefixes_and_caps_the_gloss_and_drops_junk():
    assert _env(english_gloss="Total 58.5")["english_gloss"] == "English: Total 58.5"
    assert _env(english_gloss="English: already there")["english_gloss"] == "English: already there"
    assert len(_env(english_gloss="x" * 1000)["english_gloss"]) == GLOSS_MAX
    for junk in (None, "", "   ", ["list"], 5):
        assert "english_gloss" not in _env(english_gloss=junk)
    assert "known:" not in _env(english_gloss="Total (known: home store DS-07)")["english_gloss"]


def test_english_reply_never_keeps_a_gloss():
    env = _env("Your total is 58.5", english_gloss="Total 58.5")
    resolve_gloss(env, None, lambda e: "should not be asked")
    assert "english_gloss" not in env


def test_model_gloss_kept_when_it_adds_no_number():
    env = _env(english_gloss="Total is 58.50 rupees")  # 58.50 == 58.5
    resolve_gloss(env, None, None)
    assert env["english_gloss"] == "English: Total is 58.50 rupees"


def test_gloss_with_a_number_the_reply_lacks_falls_back_to_the_template():
    env = _env(english_gloss="Total is 99")
    resolve_gloss(env, None, lambda e: "Offer: bundle for ₹58.5.")
    assert env["english_gloss"] == "English: Offer: bundle for ₹58.5."


def test_missing_gloss_uses_the_template_and_without_one_stays_absent():
    env = _env()
    resolve_gloss(env, None, lambda e: "Offer: bundle.")
    assert env["english_gloss"] == "English: Offer: bundle."
    env = _env()
    resolve_gloss(env, None, lambda e: None)
    assert "english_gloss" not in env


def test_tool_gloss_wins_over_the_models():
    env = _env(english_gloss="Total is 58.5, sir")
    resolve_gloss(env, "Your order is placed. Total 58.5.", None)
    assert env["english_gloss"] == "English: Your order is placed. Total 58.5."


def test_kannada_digits_in_the_reply_count_as_numbers():
    env = _env("ಒಟ್ಟು ₹೫೮.೫", english_gloss="Total 58.5")
    resolve_gloss(env, None, None)
    assert env["english_gloss"] == "English: Total 58.5"


def test_offer_summary_from_structured_fields():
    names = {"SKU-A": "Masala Chips 200G", "SKU-B": "Cola Classic 250ML"}
    bundle = {"sku": "SKU-A", "mechanic": "bundle", "mechanic_params": {"bundle_sku": "SKU-B", "bundle_price": 58.5}, "best_before_date": "2026-09-18"}
    assert offer_summary_en(bundle, names) == "Offer: Masala Chips 200G with Cola Classic 250ML for ₹58.5. Best before 18 Sep 2026."
    assert offer_summary_en({"sku": "SKU-A", "mechanic": "coupon", "mechanic_params": {"discount_pct": 15}}, names) == "Offer: 15% off Masala Chips 200G."
    assert offer_summary_en({"sku": "SKU-A", "mechanic": "outlet_markdown", "mechanic_params": {"markdown_pct": 10}}, names) == "Offer: 10% off Masala Chips 200G in store."


@pytest.fixture
def meena(sandbox):
    reset_sessions()
    approve(sandbox, load_tenant(), PLAY, datetime(2026, 9, 12, 9, 0, tzinfo=UTC))
    assert next(c for c in sandbox.read("customers") if c["customer_id"] == "CUST-MEENA")["language"] == "kn"
    return "CUST-MEENA"


def _chat(sandbox, cid, text):
    return asyncio.run(run_chat_async(sandbox, f"{cid}:web", text, now_iso=NOW))[0]


def test_kannada_offer_delivery_gets_the_template_gloss(meena, sandbox):
    """The offer a customer holds carries Kannada wording (a Kannada copy variant): the stub, like
    the model, delivers it as is with no gloss of its own, so the template from the offer's own
    fields fills in."""
    rows = sandbox.read("offers")
    for o in rows:
        if o["customer_id"] == meena:
            o["text"] = "ಮಸಾಲಾ ಚಿಪ್ಸ್ ಜೊತೆ ಕೋಲಾ ಕ್ಲಾಸಿಕ್ ₹50ಕ್ಕೆ. ಬಳಕೆಗೆ ಉತ್ತಮ 15 Oct 2026ರವರೆಗೆ."
    sandbox.write("offers", rows)
    env = _chat(sandbox, meena, "")
    assert env["text"].startswith("ಮಸಾಲಾ")
    assert env["english_gloss"] == "English: Offer: Masala Chips 200G with Cola Classic 250ML for ₹50. Best before 15 Oct 2026."


def test_stub_model_glosses_its_kannada_replies(meena, sandbox):
    greet = _chat(sandbox, meena, "ನಮಸ್ಕಾರ")
    assert greet["text"] != greet["english_gloss"] and greet["english_gloss"].startswith("English: ")
    assert greet["english_gloss"].startswith("English: I can check stock and offers")


def test_kannada_receipt_and_refusal_carry_their_english_twin_from_the_tool(meena, sandbox):
    from agents.customer.context import CustomerContext, reset_context, set_context
    from agents.customer.tools import place_order

    ctx = CustomerContext.build(sandbox, meena, NOW, load_tenant())
    ctx.reply_lang = "kn"
    tok = set_context(ctx)
    try:
        out = asyncio.run(place_order(meena, "DS-07", [{"sku": "SKU-MASALA-CHIPS-200G", "qty": 1}], PLAY))
        assert out["reply"].startswith("ಆರ್ಡರ್") and "50" in out["reply"]
        assert out["reply_en"] == f"Your order for Masala Chips 200G + Cola Classic 250ML has been placed. Your order ID is {out['order_id']} and the total is ₹50."
        again = asyncio.run(place_order(meena, "DS-07", [{"sku": "SKU-MASALA-CHIPS-200G", "qty": 1}], PLAY))
        assert again["reply"].startswith("ಈ ಆಫರ್") and again["reply_en"] == "This offer has already been used on your account."
    finally:
        reset_context(tok)


def test_english_reply_from_a_kannada_customer_has_no_gloss(sandbox):
    # no approved play, so no pending offer is delivered in Kannada first: the reply is plain English
    reset_sessions()
    assert "english_gloss" not in _chat(sandbox, "CUST-MEENA", "hello")
