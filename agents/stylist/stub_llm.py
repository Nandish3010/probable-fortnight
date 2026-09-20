"""Scripted stand-in for Gemini in the Stylist Agent (TAAL_MODEL_BACKEND=stub).

Same ADK plumbing as production (LlmAgent, tools, sessions); the decision policy is a script over
intents: greeting / pairing ask / item view / search / skin-tone declare-or-confirm / forget /
checkout-not-wired / STOP. It replies with the JSON envelope the prompt asks Gemini for, so the
runner parses both identically.
"""
from __future__ import annotations

import json
import re
from collections.abc import AsyncGenerator
from typing import Any

from google.adk.models import BaseLlm, LlmRequest, LlmResponse
from google.genai import types

from agents.chat_runtime import detect_lang
from data.generator.apparel import GARMENTS
from data.generator.catalog import (
    FORBIDDEN_WORDS,  # noqa: F401  (kept importable for symmetry with customer stub)
)

from .colour import SINGLE_WORD_ALIASES

STRINGS = {
    "en": {
        "greet": "Hello! Tell me a garment or show me a photo and I will suggest what goes with it.",
        "greet_recall": "Hello! Last time you looked for {desc}. Want more ideas, or something new?",
        "ask_garment": "I could not tell which garment you mean. Try \"what goes with a mustard kurta\"?",
        "pairs_intro": "For {desc}, here is what pairs well:",
        "pairs_intro_profile": "Going by your {undertone} undertone, for {desc}, here is what pairs well:",
        "pairs_intro_unknown": "I don't know that colour, so here are neutral pieces that go with {desc}:",
        "no_pairs": "I could not find anything in stock at your store that pairs with {desc} right now.",
        "item_found": "{name}: {colour}, {pattern}, ₹{price:.0f}.",
        "item_not_found": "I don't have that item in the catalogue.",
        "matches": "Here is what I found for \"{q}\" at your store:",
        "nomatch": "Nothing matching \"{q}\" is in stock at your store right now.",
        "not_sure": "I think this is {desc}, but I'm not sure.",
        "selfie_guess": "From your photo, I'd guess a {undertone} undertone, {depth} depth. Is that right?",
        "selfie_unclear": "I could not read your skin tone from that photo clearly. Which suits you best?",
        "declare_prompt": "Which suits your skin tone best? A selfie works too.",
        "tone_saved": "Saved: {undertone} undertone, {depth} depth. I will use it in pairing suggestions.",
        "forgotten": "Done. I have forgotten your skin-tone profile.",
        "no": "No problem. Ask me anytime.",
        "order_not_wired": "Checkout for apparel is not available in this build yet -- I have kept this look in mind. Want more suggestions?",
        "stop": "Understood, goodbye!",
        "unknown": "I can suggest apparel and pairings at your Kutumb Mart store. Tell me a garment, or show me a photo.",
    },
    "kn": {
        "greet": "ನಮಸ್ಕಾರ! ಯಾವುದೇ ಉಡುಪು ಹೇಳಿ ಅಥವಾ ಫೋಟೋ ತೋರಿಸಿ, ಏನು ಚೆನ್ನಾಗಿ ಹೊಂದುತ್ತದೆ ಎಂದು ಸಲಹೆ ನೀಡುತ್ತೇನೆ.",
        "greet_recall": "ನಮಸ್ಕಾರ! ಕಳೆದ ಬಾರಿ ನೀವು {desc} ಹುಡುಕಿದ್ದಿರಿ. ಇನ್ನಷ್ಟು ಸಲಹೆ ಬೇಕೇ?",
        "ask_garment": "ಯಾವ ಉಡುಪು ಎಂದು ತಿಳಿಯಲಿಲ್ಲ. \"ಸಾಸಿವೆ ಬಣ್ಣದ ಕುರ್ತಾಗೆ ಏನು ಹೊಂದುತ್ತದೆ\" ಎಂದು ಕೇಳಿ?",
        "pairs_intro": "{desc} ಗೆ ಚೆನ್ನಾಗಿ ಹೊಂದುವುದು:",
        "pairs_intro_profile": "ನಿಮ್ಮ {undertone} ಅಂಡರ್‌ಟೋನ್ ಪ್ರಕಾರ, {desc} ಗೆ ಹೊಂದುವುದು:",
        "pairs_intro_unknown": "ಆ ಬಣ್ಣ ನನಗೆ ಗೊತ್ತಿಲ್ಲ, ಆದ್ದರಿಂದ {desc} ಗೆ ಹೊಂದುವ ನ್ಯೂಟ್ರಲ್ ಬಣ್ಣಗಳು:",
        "no_pairs": "{desc} ಗೆ ಹೊಂದುವ ಯಾವುದೂ ಈಗ ನಿಮ್ಮ ಸ್ಟೋರ್‌ನಲ್ಲಿ ಸ್ಟಾಕ್‌ನಲ್ಲಿ ಇಲ್ಲ.",
        "item_found": "{name}: {colour}, {pattern}, ₹{price:.0f}.",
        "item_not_found": "ಆ ಐಟಂ ಕ್ಯಾಟಲಾಗ್‌ನಲ್ಲಿ ಇಲ್ಲ.",
        "matches": "\"{q}\" ಗಾಗಿ ನಿಮ್ಮ ಸ್ಟೋರ್‌ನಲ್ಲಿ ಸಿಕ್ಕಿದ್ದು:",
        "nomatch": "\"{q}\" ಗೆ ಹೊಂದುವ ಯಾವುದೂ ಈಗ ಸ್ಟಾಕ್‌ನಲ್ಲಿ ಇಲ್ಲ.",
        "not_sure": "ಇದು {desc} ಎಂದು ಅನ್ನಿಸುತ್ತದೆ, ಆದರೆ ಖಚಿತವಿಲ್ಲ.",
        "selfie_guess": "ನಿಮ್ಮ ಫೋಟೋದಿಂದ, {undertone} ಅಂಡರ್‌ಟೋನ್, {depth} ಡೆಪ್ತ್ ಎಂದು ಊಹಿಸುತ್ತೇನೆ. ಸರಿಯೇ?",
        "selfie_unclear": "ಆ ಫೋಟೋದಿಂದ ಸ್ಪಷ್ಟವಾಗಿ ತಿಳಿಯಲಿಲ್ಲ. ಯಾವುದು ನಿಮಗೆ ಸೂಕ್ತ?",
        "declare_prompt": "ನಿಮ್ಮ ಚರ್ಮದ ಬಣ್ಣಕ್ಕೆ ಯಾವುದು ಸೂಕ್ತ? ಸೆಲ್ಫಿಯೂ ಕೆಲಸ ಮಾಡುತ್ತದೆ.",
        "tone_saved": "ಉಳಿಸಲಾಗಿದೆ: {undertone} ಅಂಡರ್‌ಟೋನ್, {depth} ಡೆಪ್ತ್. ಸಲಹೆಗಳಲ್ಲಿ ಬಳಸುತ್ತೇನೆ.",
        "forgotten": "ಆಯಿತು. ನಿಮ್ಮ ಚರ್ಮದ ಬಣ್ಣದ ಪ್ರೊಫೈಲ್ ಅಳಿಸಲಾಗಿದೆ.",
        "no": "ಪರವಾಗಿಲ್ಲ. ಯಾವಾಗ ಬೇಕಾದರೂ ಕೇಳಿ.",
        "order_not_wired": "ಈ ಬಿಲ್ಡ್‌ನಲ್ಲಿ ಬಟ್ಟೆ ಆರ್ಡರ್ ಇನ್ನೂ ಲಭ್ಯವಿಲ್ಲ -- ಈ ಲುಕ್ ನೆನಪಿಟ್ಟುಕೊಂಡಿದ್ದೇನೆ. ಇನ್ನಷ್ಟು ಸಲಹೆ ಬೇಕೇ?",
        "stop": "ಆಯಿತು, ವಿದಾಯ!",
        "unknown": "ನಿಮ್ಮ ಕುಟುಂಬ ಮಾರ್ಟ್ ಸ್ಟೋರ್‌ನಲ್ಲಿ ಬಟ್ಟೆ ಮತ್ತು ಜೋಡಣೆ ಸಲಹೆ ನೀಡಬಲ್ಲೆ. ಒಂದು ಉಡುಪು ಹೇಳಿ ಅಥವಾ ಫೋಟೋ ತೋರಿಸಿ.",
    },
}
LABELS = {
    "en": {"yes": "Yes, that's me", "cooler": "Cooler", "neutral": "Neutral", "no": "Not now", "pair": "What goes with it", "warm": "Warm", "cool": "Cool"},
    "kn": {"yes": "ಹೌದು", "cooler": "ತಂಪಾದದ್ದು", "neutral": "ನ್ಯೂಟ್ರಲ್", "no": "ಈಗ ಬೇಡ", "pair": "ಇದಕ್ಕೆ ಏನು ಹೊಂದುತ್ತದೆ", "warm": "ಬೆಚ್ಚಗಿನ", "cool": "ತಂಪಾದ"},
}

GREETING_RE = re.compile(r"^\W*(hi|hello|hey|namaskara|namaste|good (morning|evening))\W*$|^\W*(ನಮಸ್ಕಾರ|ನಮಸ್ತೆ)\W*$")
STOP_RE = re.compile(r"^\W*(stop|bye|goodbye|thanks bye|thank you bye)\W*$", re.I)
ORDER_RE = re.compile(r"\b(add|order|buy|checkout|cart)\b", re.I)
PAIR_RE = re.compile(r"\b(what (goes|works) with|goes? with|pair|match(es)?|style (this|my)|outfit|complete the look)\b", re.I)
OCCASION_WORDS = ("casual", "office", "festive", "wedding", "party", "travel")
FORGET_RE = re.compile(r"\bforget\b.*\b(skin|profile|tone)\b|\bdelete\b.*\bprofile\b", re.I)
SKIN_ASK_RE = re.compile(r"\b(skin tone|undertone|my skin|skin colou?r)\b", re.I)
TONE_BUTTON_RE = re.compile(r"^tone:(selfie|declared):(warm|cool|neutral):(light|medium|deep)$")
ITEM_RE = re.compile(r"^item:(\S+)$")
PAIR_BUTTON_RE = re.compile(r"^pair:(\S+)$")
SELFIE_SUFFIX_RE = re.compile(r"\(selfie: ([a-z]+) undertone, ([a-z]+) depth, confidence ([\d.]+)\)|\(selfie: unclear\)")
PHOTO_SUFFIX_RE = re.compile(r"\(photo: (.+?)(, not sure)?\)$")
CUST_RE = re.compile(r"customer_id=([A-Za-z0-9_-]+)")

_GARMENT_WORDS = set(GARMENTS)
for _spec in GARMENTS.values():
    _GARMENT_WORDS.update(_spec.get("synonyms", []))
_COLOUR_WORDS = set(SINGLE_WORD_ALIASES)


class StubStylistLlm(BaseLlm):
    model: str = "stub-stylist"
    apparel: dict[str, dict] = {}

    @classmethod
    def supported_models(cls) -> list[str]:
        return [r"stub-stylist.*"]

    def _call(self, name: str, args: dict[str, Any]) -> LlmResponse:
        return LlmResponse(content=types.Content(role="model", parts=[types.Part(function_call=types.FunctionCall(name=name, args=args))]))

    def _say(self, payload: dict[str, Any]) -> LlmResponse:
        return LlmResponse(content=types.Content(role="model", parts=[types.Part(text=json.dumps(payload, ensure_ascii=False))]))

    def _turn(self, req: LlmRequest) -> tuple[str, str, list[tuple[str, dict]], list[tuple[str, dict]]]:
        customer_id, last_user, calls, responses = "", "", [], []
        for c in req.contents:
            for part in c.parts or []:
                if part.text and c.role == "user":
                    m = CUST_RE.search(part.text)
                    if m:
                        customer_id = m.group(1)
                    last_user = part.text
                    calls, responses = [], []
                if part.function_call:
                    calls.append((part.function_call.name, dict(part.function_call.args or {})))
                if part.function_response:
                    responses.append((part.function_response.name, dict(part.function_response.response or {})))
        return customer_id, last_user, calls, responses

    async def generate_content_async(self, llm_request: LlmRequest, stream: bool = False) -> AsyncGenerator[LlmResponse, None]:
        yield self.decide(llm_request)

    def decide(self, req: LlmRequest) -> LlmResponse:
        customer_id, user, calls, responses = self._turn(req)
        text = re.sub(r"customer_id=\S+\s*", "", user).strip()
        by = {n: r for n, r in responses}
        ctx = by.get("get_style_context")
        if ctx is None:
            return self._call("get_style_context", {"customer_id": customer_id})
        low = text.lower()
        lang = detect_lang(text, ctx.get("language") or "en")
        s, lab = STRINGS.get(lang, STRINGS["en"]), LABELS.get(lang, LABELS["en"])
        node = ctx["home_node_id"]

        if STOP_RE.match(low):
            return self._say({"text": s["stop"]})
        if ORDER_RE.search(low):
            return self._say({"text": s["order_not_wired"]})
        if FORGET_RE.search(low):
            if "forget_style_profile" not in by:
                return self._call("forget_style_profile", {"customer_id": customer_id})
            return self._say({"text": s["forgotten"]})

        m_item = ITEM_RE.match(low)
        if m_item:
            sku = m_item.group(1).upper()
            if "describe_item" not in by:
                return self._call("describe_item", {"sku": sku})
            it = by["describe_item"]
            if not it.get("found"):
                return self._say({"text": s["item_not_found"]})
            return self._say({"text": s["item_found"].format(name=it["name"], colour=it["colour"], pattern=it.get("pattern") or "solid", price=float(it["list_price"])), "buttons": [{"id": f"pair:{sku}", "label": lab["pair"]}, {"id": "no", "label": lab["no"]}]})

        m_tone = TONE_BUTTON_RE.match(low)
        if m_tone:
            source_kind, undertone, depth = m_tone.groups()
            source = "selfie" if source_kind == "selfie" else "declared"
            if "set_style_profile" not in by:
                return self._call("set_style_profile", {"customer_id": customer_id, "undertone": undertone, "depth": depth, "source": source})
            return self._say({"text": s["tone_saved"].format(undertone=undertone, depth=depth)})

        m_photo = PHOTO_SUFFIX_RE.search(text)
        m_selfie = SELFIE_SUFFIX_RE.search(text)
        if m_selfie:
            if m_selfie.group(1):
                undertone, depth = m_selfie.group(1), m_selfie.group(2)
                return self._say({
                    "text": s["selfie_guess"].format(undertone=undertone, depth=depth),
                    "buttons": [
                        {"id": f"tone:selfie:{undertone}:{depth}", "label": lab["yes"]},
                        {"id": f"tone:selfie:{'cool' if undertone != 'cool' else 'warm'}:{depth}", "label": lab["cooler"] if undertone == "warm" else lab["warm"]},
                        {"id": f"tone:selfie:neutral:{depth}", "label": lab["neutral"]},
                    ],
                })
            return self._say({"text": s["selfie_unclear"], "buttons": [{"id": "tone:declared:warm:medium", "label": lab["warm"]}, {"id": "tone:declared:cool:medium", "label": lab["cool"]}, {"id": "tone:declared:neutral:medium", "label": lab["neutral"]}]})
        if SKIN_ASK_RE.search(low) and not m_photo:
            return self._say({"text": s["declare_prompt"], "buttons": [{"id": "tone:declared:warm:medium", "label": lab["warm"]}, {"id": "tone:declared:cool:medium", "label": lab["cool"]}, {"id": "tone:declared:neutral:medium", "label": lab["neutral"]}]})

        m_pair_btn = PAIR_BUTTON_RE.match(low)
        wants_pairing = bool(m_pair_btn) or PAIR_RE.search(low) or bool(m_photo)
        if wants_pairing:
            if "suggest_pairings" not in by:
                anchor = m_pair_btn.group(1).upper() if m_pair_btn else text
                occasion = next((o for o in OCCASION_WORDS if o in low), None)
                return self._call("suggest_pairings", {"anchor": anchor, "node_id": node, "occasion": occasion})
            res = by["suggest_pairings"]
            anchor = res["anchor"]
            desc = anchor.get("description") or "that"
            prefix = ""
            if m_photo and m_photo.group(2):
                prefix = s["not_sure"].format(desc=desc) + " "
            if not anchor.get("garment_type"):
                return self._say({"text": prefix + s["ask_garment"]})
            if not res.get("fulfilled"):
                return self._say({"text": prefix + s["no_pairs"].format(desc=desc)})
            if res.get("profile_applied") and ctx.get("style_profile"):
                intro = s["pairs_intro_profile"].format(undertone=ctx["style_profile"]["undertone"], desc=desc)
            elif not anchor.get("known_colour"):
                intro = s["pairs_intro_unknown"].format(desc=desc)
            else:
                intro = s["pairs_intro"].format(desc=desc)
            rows = []
            for p in res["pairings"][:10]:
                note = f" · {p['skin_note']}" if p.get("skin_note") else ""
                rows.append({"id": f"item:{p['sku']}", "title": p["name"][:24], "desc": f"{p['role']} · {p['reason']}{note} · ₹{p['list_price']:.0f}"[:72]})
            citations = [{"type": "stock", "ref": f"{p['sku']}@{node}"} for p in res["pairings"][:3]]
            if anchor.get("sku"):
                citations.append({"type": "stock", "ref": f"{anchor['sku']}@{node}"})
            return self._say({"text": prefix + intro, "list": {"title": "Pairs well", "rows": rows}, "citations": citations})

        if low in ("no", "not now", "no thanks"):
            return self._say({"text": s["no"]})

        garment_word = next((w for w in re.findall(r"[a-z]+", low) if w in _GARMENT_WORDS), None)
        colour_word = next((w for w in re.findall(r"[a-z]+", low) if w in _COLOUR_WORDS), None)
        occasion_word = next((o for o in OCCASION_WORDS if o in low), None)
        if garment_word or colour_word or occasion_word:
            if "find_apparel" not in by:
                return self._call("find_apparel", {"query": text, "node_id": node})
            res = by["find_apparel"]
            items = res.get("items") or []
            if not items:
                return self._say({"text": s["nomatch"].format(q=text)})
            rows = [{"id": f"item:{it['sku']}", "title": it["name"][:24], "desc": f"{it['role']} · ₹{it['list_price']:.0f}"[:72]} for it in items[:10]]
            return self._say({"text": s["matches"].format(q=text), "list": {"title": "In stock", "rows": rows}, "citations": [{"type": "stock", "ref": f"{it['sku']}@{node}"} for it in items[:3]]})

        if GREETING_RE.match(low) or not text:
            asks = ctx.get("recent_asks") or []
            top = next((a for a in asks if a.get("garment_type")), None)
            if top:
                desc = " ".join(x for x in (top.get("colour_family"), top.get("garment_type")) if x)
                return self._say({"text": s["greet_recall"].format(desc=desc)})
            return self._say({"text": s["greet"]})

        return self._say({"text": s["unknown"]})
