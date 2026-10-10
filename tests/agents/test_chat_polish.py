"""Customer chat polish: no dangling ")" on a reply, an action-id click keeps the customer's
language (Kannada receipt with its English gloss), and every quick reply carries a distinct label."""
import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from google.adk.agents import LlmAgent
from google.adk.models import BaseLlm, LlmResponse
from google.genai import types

from agents.chat_runtime import clamp, detect_lang, drop_dangling_close
from agents.customer.chat import RUNTIME, reset_sessions, run_chat_async
from agents.gate.config import load_tenant
from services.api.approve import approve

PLAY = "play_chips_ds07_v1"
CHIPS = "SKU-MASALA-CHIPS-200G"
NOW = "2026-09-12T09:05:00Z"
CONVOS = sorted((Path(__file__).resolve().parents[2] / "fixtures" / "conversations").glob("*.json"))


def dangling(text: str) -> bool:
    t = text.rstrip()
    return t.endswith(")") and t.count(")") > t.count("(")


def _all_texts(env):
    yield env["text"]
    yield env.get("english_gloss", "")
    for b in env.get("buttons") or []:
        yield b["label"]
    for r in (env.get("list") or {}).get("rows", []):
        yield r["title"]


def test_dangling_close_is_dropped_but_a_closed_paren_stays():
    assert drop_dangling_close("Best before 2026-10-15. )") == "Best before 2026-10-15."
    assert drop_dangling_close("Few left (only 3)") == "Few left (only 3)"
    assert clamp({"text": "In stock. )"})["text"] == "In stock."


def test_echoed_note_with_a_nested_parenthesis_is_removed_whole():
    note = '(known: home store DS-07; reply in English for this turn; previously asked about Cola Zero 500ML (still not in stock))'
    assert clamp({"text": f"Cola Classic 500ML in stock. {note}"})["text"] == "Cola Classic 500ML in stock."
    assert clamp({"text": "Hello (known: home store DS-07; never closed"})["text"] == "Hello"


class EchoNoteLlm(BaseLlm):
    """A live model that quotes the per-turn context note after its answer."""
    model: str = "stub-echo"

    async def generate_content_async(self, llm_request, stream=False):
        user = next(p.text for c in reversed(llm_request.contents) if c.role == "user" for p in c.parts if p.text)
        note = user[user.index("(known:"):]
        yield LlmResponse(content=types.Content(role="model", parts=[types.Part(text=json.dumps({"text": f"We have a bundle deal on Masala Chips 200G. {note}"}))]))


def test_live_path_reply_never_ends_with_a_dangling_paren(sandbox, monkeypatch):
    """The vertex path folds `(known: ...)` into the turn; a model that echoes it must not leave a ")"."""
    monkeypatch.setattr(RUNTIME, "_build_agent", lambda store, backend: LlmAgent(name="customer", model=EchoNoteLlm(), instruction="x", tools=[]))
    reset_sessions()
    approve(sandbox, load_tenant(), PLAY, datetime(2026, 9, 12, 9, 0, tzinfo=UTC))
    rows = sandbox.read("customer_requests")
    rows.append({"tenant_id": "kutumb-mart", "customer_id": "CUST-MEENA", "node_id": "DS-07", "sku": "SKU-COLA-ZERO-500ML", "query_text": None, "request_type": "out_of_stock", "session_id": "CUST-MEENA:web", "ts": "2026-09-11T09:00:00Z"})
    sandbox.write("customer_requests", rows)
    env = asyncio.run(run_chat_async(sandbox, "CUST-MEENA:web", "Any offers today?", backend="vertex", now_iso=NOW))[0]
    assert "known" not in env["text"] and not dangling(env["text"]), env["text"]
    assert env["text"] == "We have a bundle deal on Masala Chips 200G."


@pytest.mark.parametrize("path", CONVOS, ids=[p.stem for p in CONVOS])
def test_no_scripted_reply_ends_with_an_unmatched_close_paren(path, sandbox):
    convo = json.loads(path.read_text(encoding="utf-8"))
    reset_sessions()
    play = convo["setup"].get("approve_play")
    if play:
        approve(sandbox, load_tenant(), play, datetime(2026, 9, 12, 9, 0, tzinfo=UTC))
    cid = convo["customer_id"]
    if cid.startswith("__"):
        lang = {c["customer_id"]: c.get("language") for c in sandbox.read("customers")}
        rows = [a for a in sandbox.read("play_assignments") if a["play_id"] == play]
        cid = next(a["customer_id"] for a in rows if (a["arm"] == "holdout") == (cid == "__HOLDOUT__") and (cid == "__HOLDOUT__" or lang.get(a["customer_id"]) == ("kn" if cid == "__TREATED_KN__" else "en")))
    for turn in convo["turns"]:
        env = asyncio.run(run_chat_async(sandbox, f"{cid}:web", turn["text"], now_iso=NOW))[0]
        for t in _all_texts(env):
            assert not dangling(t), (path.stem, t)


@pytest.mark.parametrize("text", [f"add:{CHIPS}", "cat:snacks", "no", "stop", "STOP", ""])
def test_action_ids_follow_the_stored_language(text):
    assert detect_lang(text, "kn") == "kn" and detect_lang(text, "en") == "en"
    assert detect_lang("add masala chips", "kn") == "en" and detect_lang("ಹಾಯ್", "en") == "kn"


@pytest.fixture
def meena(sandbox):
    reset_sessions()
    approve(sandbox, load_tenant(), PLAY, datetime(2026, 9, 12, 9, 0, tzinfo=UTC))
    assert next(c for c in sandbox.read("customers") if c["customer_id"] == "CUST-MEENA")["language"] == "kn"
    return "CUST-MEENA"


def test_kannada_customer_add_to_cart_gets_a_kannada_receipt_with_gloss(sandbox, meena):
    env = asyncio.run(run_chat_async(sandbox, f"{meena}:web", f"add:{CHIPS}", now_iso=NOW))[0]
    order = next(o for o in sandbox.read("orders") if o["customer_id"] == meena and o["ts"] == NOW)
    assert env["text"].startswith("ಆರ್ಡರ್") and order["order_id"] in env["text"] and "58.5" in env["text"]
    assert env["english_gloss"] == f"English: Your order for Masala Chips 200G + Coconut Water 1L has been placed. Your order ID is {order['order_id']} and the total is ₹58.5."


def test_kannada_customer_no_button_replies_in_kannada(sandbox, meena):
    env = asyncio.run(run_chat_async(sandbox, f"{meena}:web", "no", now_iso=NOW))[0]
    assert env["text"].startswith("ಪರವಾಗಿಲ್ಲ") and env["english_gloss"].startswith("English: No problem")


def test_every_quick_reply_has_a_distinct_human_label_in_both_languages():
    kn = "ಮಸಾಲಾ ಚಿಪ್ಸ್ ಮೇಲೆ ಬಂಡಲ್ ಡೀಲ್"
    for text, lang in ((kn, "kn"), ("A bundle deal", "en")):
        env = clamp({"text": text, "buttons": [
            {"id": f"add:{CHIPS}", "label": "add:SKU"}, {"id": "no", "label": "ಬೇಡ"}, {"id": "stop", "label": "ಬೇಡ"}, {"id": "x"}]})
        labels = [b["label"] for b in env["buttons"]]
        assert len(labels) == 3 and len(set(labels)) == 3 and all(x and ":" not in x for x in labels), labels
        assert labels[0] == ("ಕಾರ್ಟ್‌ಗೆ ಸೇರಿಸಿ" if lang == "kn" else "Add to cart")
    rows = clamp({"text": "x", "list": {"title": "t", "rows": [{"id": "add:SKU-A"}, {"id": "cat:dairy", "desc": "Milk"}]}})["list"]["rows"]
    assert [r["title"] for r in rows] == ["Sku A", "Milk"]


class EnglishOnlyLlm(BaseLlm):
    """A model that ignores the Kannada directive."""
    model: str = "stub-english"
    text: str = "We have a bundle deal on Masala Chips 200G for Rs 58.5. Best before 2026-10-15."

    async def generate_content_async(self, llm_request, stream=False):
        yield LlmResponse(content=types.Content(role="model", parts=[types.Part(text=json.dumps({"text": self.text}))]))


def _english_model(monkeypatch, text=None):
    llm = EnglishOnlyLlm(**({"text": text} if text else {}))
    monkeypatch.setattr(RUNTIME, "_build_agent", lambda store, backend: LlmAgent(name="customer", model=llm, instruction="x", tools=[]))
    reset_sessions()


def test_english_reply_on_a_kannada_turn_becomes_kannada_with_the_english_gloss(sandbox, meena, monkeypatch):
    _english_model(monkeypatch)
    env = asyncio.run(run_chat_async(sandbox, f"{meena}:web", "ಇಂದು ಯಾವ ಆಫರ್ ಇದೆ?", now_iso=NOW))[0]
    assert env["text"].startswith("Masala Chips 200G ಜೊತೆ Coconut Water 1L ₹58.5ಕ್ಕೆ") and "ಬಳಕೆಗೆ ಉತ್ತಮ" in env["text"]
    assert env["english_gloss"].startswith("English: ") and "58.5" in env["english_gloss"]


def test_english_reply_with_no_kannada_rendering_gets_a_kannada_notice_and_gloss(sandbox, meena, monkeypatch):
    _english_model(monkeypatch, "Sure, anything else?")
    env = asyncio.run(run_chat_async(sandbox, f"{meena}:web", "ಧನ್ಯವಾದ", now_iso=NOW))[0]
    assert env["text"].startswith("ಕ್ಷಮಿಸಿ") and env["english_gloss"] == "English: Sure, anything else?"


def test_english_message_from_a_kannada_customer_may_get_an_english_reply(sandbox, meena, monkeypatch):
    _english_model(monkeypatch, "Sure, anything else?")
    env = asyncio.run(run_chat_async(sandbox, f"{meena}:web", "thanks", now_iso=NOW))[0]
    assert env["text"] == "Sure, anything else?" and "english_gloss" not in env
