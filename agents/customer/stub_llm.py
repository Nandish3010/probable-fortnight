"""Scripted stand-in for Gemini in the Customer Agent (TAAL_MODEL_BACKEND=stub).

Same ADK plumbing as production (LlmAgent, tools, sessions); the decision policy is a script over
intents: offers / product question / add / order / STOP. It replies with the JSON envelope the
prompt asks Gemini for, so the runner parses both identically.
"""
from __future__ import annotations

import json
import re
from collections.abc import AsyncGenerator
from typing import Any

from google.adk.models import BaseLlm, LlmRequest, LlmResponse
from google.genai import types

STRINGS = {
    "en": {
        "greet": "Hello {name}! No offers for you today. Ask me for any product and I will check your store.",
        "in_stock": "{name} is in stock at your store{low}. Best before {bb}. Add it?",
        "oos": "{name} is out at your store right now. Here is what is on the shelf instead:",
        "none": "{name} is out at your store and I could not find a substitute in stock.",
        "ordered": "Order {order_id} placed: {items}. Total ₹{total:.0f}. Thank you!",
        "stop": "Done. You will not receive offers on chat. Reply if you need anything else.",
        "no": "No problem. Ask me anytime.",
        "refused": "That offer is not available for you: {reason}.",
        "unknown": "I can check stock and offers at your Kutumb Mart store. Which product?",
        "low_stock": " (only a few left)",
        "browse": "On the shelf at your store today:",
        "matches": "Here is what I found for \"{q}\" at your store:",
        "nomatch": "Nothing matching \"{q}\" is in stock at your store right now.",
        "no_discount": "No extra discount on {q} right now. I will let you know if one comes up.",
    },
    "kn": {
        "greet": "ನಮಸ್ಕಾರ {name}! ಇಂದು ನಿಮಗೆ ಯಾವುದೇ ಆಫರ್ ಇಲ್ಲ. ಯಾವುದೇ ಉತ್ಪನ್ನ ಕೇಳಿ, ನಿಮ್ಮ ಸ್ಟೋರ್‌ನಲ್ಲಿ ಪರಿಶೀಲಿಸುತ್ತೇನೆ.",
        "in_stock": "{name} ನಿಮ್ಮ ಸ್ಟೋರ್‌ನಲ್ಲಿ ಲಭ್ಯ{low}. ಬಳಕೆಗೆ ಉತ್ತಮ {bb}ರವರೆಗೆ. ಸೇರಿಸಲೇ?",
        "oos": "{name} ಈಗ ನಿಮ್ಮ ಸ್ಟೋರ್‌ನಲ್ಲಿ ಇಲ್ಲ. ಬದಲಿಗೆ ಶೆಲ್ಫ್‌ನಲ್ಲಿ ಇರುವುದು:",
        "none": "{name} ನಿಮ್ಮ ಸ್ಟೋರ್‌ನಲ್ಲಿ ಇಲ್ಲ ಮತ್ತು ಬದಲಿ ಸಿಗಲಿಲ್ಲ.",
        "ordered": "ಆರ್ಡರ್ {order_id} ಆಗಿದೆ: {items}. ಒಟ್ಟು ₹{total:.0f}. ಧನ್ಯವಾದಗಳು!",
        "stop": "ಆಯಿತು. ಚಾಟ್‌ನಲ್ಲಿ ಆಫರ್‌ಗಳು ಬರುವುದಿಲ್ಲ.",
        "no": "ಪರವಾಗಿಲ್ಲ. ಯಾವಾಗ ಬೇಕಾದರೂ ಕೇಳಿ.",
        "refused": "ಆ ಆಫರ್ ನಿಮಗೆ ಲಭ್ಯವಿಲ್ಲ: {reason}.",
        "unknown": "ನಿಮ್ಮ ಕುಟುಂಬ ಮಾರ್ಟ್ ಸ್ಟೋರ್‌ನ ಸ್ಟಾಕ್ ಮತ್ತು ಆಫರ್‌ಗಳನ್ನು ಪರಿಶೀಲಿಸಬಲ್ಲೆ. ಯಾವ ಉತ್ಪನ್ನ?",
        "low_stock": " (few left)",
        "browse": "ಇಂದು ನಿಮ್ಮ ಸ್ಟೋರ್‌ನ ಶೆಲ್ಫ್‌ನಲ್ಲಿ:",
        "matches": "\"{q}\" ಗಾಗಿ ನಿಮ್ಮ ಸ್ಟೋರ್‌ನಲ್ಲಿ ಸಿಕ್ಕಿದ್ದು:",
        "nomatch": "\"{q}\" ಗೆ ಹೊಂದುವ ಯಾವುದೂ ಈಗ ಸ್ಟಾಕ್‌ನಲ್ಲಿ ಇಲ್ಲ.",
        "no_discount": "{q} ಮೇಲೆ ಈಗ ಹೆಚ್ಚುವರಿ ರಿಯಾಯಿತಿ ಇಲ್ಲ. ಬಂದಾಗ ತಿಳಿಸುತ್ತೇನೆ.",
    },
}
LABELS = {"en": {"add": "Add to cart", "no": "Not now", "stop": "STOP", "subs": "In stock at your store", "cats": "Categories"}, "kn": {"add": "ಕಾರ್ಟ್‌ಗೆ ಸೇರಿಸಿ", "no": "ಈಗ ಬೇಡ", "stop": "STOP", "subs": "ನಿಮ್ಮ ಸ್ಟೋರ್‌ನಲ್ಲಿ ಲಭ್ಯ", "cats": "ವಿಭಾಗಗಳು"}}
GREETING_RE = re.compile(r"^\W*(hi|hello|hey|namaskara|namaste|good (morning|evening)|any (offers?|deals?|discounts?)( today)?\??|offers?|deals?|discounts?)\W*$|\b(offers?|deals?|discounts?)\b")
KANNADA_RE = re.compile(r"[\u0C80-\u0CFF]")
BROWSE_RE = re.compile(r"\b(what (all )?(do|can) (you|i)|what all|menu|catalog(ue)?|categories|everything|browse)\b")
SIZE_RE = re.compile(r"^\d+(g|kg|ml|l)$")
LOW_STOCK_THRESHOLD = 5  # a coarse urgency signal to the customer; never the exact count
CUST_RE = re.compile(r"customer_id=([A-Za-z0-9_-]+)")


def _fmt_date(iso: str | None) -> str:
    if not iso:
        return "-"
    from datetime import date

    return date.fromisoformat(iso).strftime("%d %b %Y")


class StubCustomerLlm(BaseLlm):
    model: str = "stub-customer"
    catalog: dict[str, str] = {}  # lowercase product name -> sku

    @classmethod
    def supported_models(cls) -> list[str]:
        return [r"stub-customer.*"]

    def _call(self, name: str, args: dict[str, Any]) -> LlmResponse:
        return LlmResponse(content=types.Content(role="model", parts=[types.Part(function_call=types.FunctionCall(name=name, args=args))]))

    def _say(self, payload: dict[str, Any]) -> LlmResponse:
        return LlmResponse(content=types.Content(role="model", parts=[types.Part(text=json.dumps(payload, ensure_ascii=False))]))

    def _turn(self, req: LlmRequest) -> tuple[str, str, list[tuple[str, dict]], list[tuple[str, dict]], list[dict]]:
        """(customer_id, latest user text, calls since that text, responses since that text,
        last_context). Decision logic below only ever acts on the latest turn's tool calls (this
        stand-in has no real reasoning over history), but `last_context` carries the last product
        list a browse/stock lookup surfaced across EARLIER turns too, so a bare follow-up like
        "any discounts?" can still refer to what was just shown instead of falling to the unknown
        reply. Real Gemini (vertex backend) sees the whole transcript and does not need this."""
        customer_id, last_user, calls, responses, last_context = "", "", [], [], []
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
                    name, resp = part.function_response.name, dict(part.function_response.response or {})
                    responses.append((name, resp))
                    if name == "list_products" and resp.get("products"):
                        last_context = resp["products"]
                    elif name == "get_stock" and resp.get("qty", 0) > 0:
                        last_context = [resp]
                    elif name == "find_substitutes":
                        subs = resp.get("result", resp) if isinstance(resp, dict) else resp
                        if subs:
                            last_context = subs
        return customer_id, last_user, calls, responses, last_context

    @staticmethod
    def _detect_lang(text: str, fallback: str) -> str:
        """Reply in the script the customer just typed in; fall back to their stored preference
        only when the message carries no script of its own (STOP, an add: id, empty)."""
        if KANNADA_RE.search(text):
            return "kn"
        if re.search(r"[A-Za-z]{2,}", text):
            return "en"
        return fallback

    def _browse_reply(self, res: dict[str, Any], q: str, s: dict[str, str], lab: dict[str, str], node: str) -> LlmResponse:
        products = res.get("products") or []
        if products:
            rows = [{"id": f"add:{p['sku']}", "title": p["name"][:24], "desc": f"₹{float(p.get('list_price') or 0):.0f}{' · few left' if p['qty'] <= LOW_STOCK_THRESHOLD else ''}"[:72]} for p in products[:10]]
            return self._say({"text": s["matches"].format(q=q), "list": {"title": lab["subs"][:60], "rows": rows}, "citations": [{"type": "stock", "ref": f"{p['sku']}@{node}"} for p in products[:3]]})
        cats = res.get("categories") or []
        if q:
            return self._say({"text": s["nomatch"].format(q=q)})
        rows = [{"id": f"cat:{c}", "title": c.replace("_", " ").title()[:24]} for c in cats[:10]]
        return self._say({"text": s["browse"], "list": {"title": lab["cats"][:60], "rows": rows}})

    def _sku_in(self, text: str) -> str | None:
        """Exact product mention: the full name without its pack size (e.g. 'cola zero', 'masala chips')."""
        low = text.lower()
        best = None
        for name, sku in self.catalog.items():
            base = name.rsplit(" ", 1)[0] if SIZE_RE.match(name.split()[-1]) else name
            if re.search(rf"\b{re.escape(base)}\b", low) and (best is None or len(base) > len(best[0])):
                best = (base, sku)
        return best[1] if best else None

    def _query_word(self, text: str) -> str | None:
        """A catalogue word mentioned in the text ('chips', 'bread', 'tea'), longest first."""
        vocab: set[str] = set()
        for name in self.catalog:
            vocab.update(w for w in name.lower().split() if len(w) >= 3 and not SIZE_RE.match(w))
        words = [w for w in re.findall(r"[a-z]+", text.lower())]
        cands = [w for w in words if w in vocab or (w.endswith("s") and w[:-1] in vocab)]
        return max(cands, key=len) if cands else None

    async def generate_content_async(self, llm_request: LlmRequest, stream: bool = False) -> AsyncGenerator[LlmResponse, None]:
        yield self.decide(llm_request)

    def decide(self, req: LlmRequest) -> LlmResponse:
        customer_id, user, calls, responses, last_context = self._turn(req)
        text = re.sub(r"customer_id=\S+\s*", "", user).strip()
        by = {n: r for n, r in responses}
        ctx = by.get("get_customer_context")
        if ctx is None:
            return self._call("get_customer_context", {"customer_id": customer_id})
        lang = self._detect_lang(text, ctx.get("language") or "en")
        s, lab = STRINGS.get(lang, STRINGS["en"]), LABELS.get(lang, LABELS["en"])
        name = ctx.get("display_name") or customer_id
        node = ctx["home_node_id"]
        low = text.lower()
        offers = ctx.get("pending_offers") or []
        # STOP
        if low.strip() in ("stop", "stop.", "unsubscribe"):
            if "record_stop" not in by:
                return self._call("record_stop", {"customer_id": customer_id, "channel": "web_chat"})
            return self._say({"text": s["stop"]})
        # add / order
        if low.startswith("add:") or (low.split()[:1] in (["add"], ["order"], ["yes"]) and (offers or "get_stock" in by)):
            sku = low.split(":", 1)[1].strip().upper() if low.startswith("add:") else (offers[0].get("sku") if offers else by.get("get_stock", {}).get("sku"))
            play_id = next((o["play_id"] for o in offers if o.get("sku") == sku), "") if offers else ""
            if play_id and "apply_offer" not in by:
                return self._call("apply_offer", {"play_id": play_id, "customer_id": customer_id})
            if play_id and not by["apply_offer"].get("ok"):
                return self._say({"text": s["refused"].format(reason=by["apply_offer"].get("reason", ""))})
            if "place_order" not in by:
                lines = [{"sku": sku, "qty": 1}]
                offer = by.get("apply_offer") or {}
                if offer.get("mechanic") == "bundle" and offer.get("bundle_sku"):
                    lines.append({"sku": offer["bundle_sku"], "qty": 1})
                return self._call("place_order", {"customer_id": customer_id, "node_id": node, "lines": lines, "play_id": play_id})
            po = by["place_order"]
            items = " + ".join(f"{ln['qty']}x {ln['name']}" for ln in po.get("lines") or []) or sku
            return self._say({"text": s["ordered"].format(order_id=po.get("order_id"), items=items, total=float(po.get("total_inr") or 0)), "citations": [{"type": "play", "ref": play_id}] if play_id else []})
        if low in ("no", "not now", "no thanks"):
            return self._say({"text": s["no"]})
        # category button or browse
        if low.startswith("cat:") or BROWSE_RE.search(low):
            q = low.split(":", 1)[1].strip() if low.startswith("cat:") else ""
            if "list_products" not in by:
                return self._call("list_products", {"query": q, "node_id": node})
            return self._browse_reply(by["list_products"], q, s, lab, node)
        # product question
        sku = self._sku_in(text)
        if not sku and not GREETING_RE.search(low):
            q = self._query_word(text)
            if q:
                if "list_products" not in by:
                    return self._call("list_products", {"query": q, "node_id": node})
                return self._browse_reply(by["list_products"], q, s, lab, node)
        if sku:
            if "get_stock" not in by:
                return self._call("get_stock", {"sku": sku, "node_id": node})
            st = by["get_stock"]
            if st.get("qty", 0) > 0:
                low = s["low_stock"] if st["qty"] <= LOW_STOCK_THRESHOLD else ""
                return self._say({"text": s["in_stock"].format(name=st.get("name", sku), low=low, bb=_fmt_date(st.get("expiry_date"))), "buttons": [{"id": f"add:{sku}", "label": lab["add"]}, {"id": "no", "label": lab["no"]}], "citations": [{"type": "stock", "ref": st.get("batch_id") or f"{sku}@{node}"}]})
            if "find_substitutes" not in by:
                return self._call("find_substitutes", {"sku": sku, "node_id": node})
            subs = by["find_substitutes"].get("result", by["find_substitutes"]) if isinstance(by["find_substitutes"], dict) else by["find_substitutes"]
            if not subs:
                return self._say({"text": s["none"].format(name=st.get("name", sku))})
            rows = [{"id": f"add:{r['sku']}", "title": r["name"][:24], "desc": f"₹{float(r.get('list_price') or 0):.0f}{' · few left' if r['qty'] <= LOW_STOCK_THRESHOLD else ''}"[:72]} for r in subs[:10]]
            return self._say({"text": s["oos"].format(name=st.get("name", sku)), "list": {"title": lab["subs"][:60], "rows": rows}, "citations": [{"type": "stock", "ref": f"{sku}@{node}"}] + [{"type": "stock", "ref": f"{r['sku']}@{node}"} for r in subs[:3]]})
        # a bare discount/offer question with something just shown and nothing pending: say so
        # against what she was just looking at, instead of the generic "which product?" fallback
        if not offers and last_context and "discount" in low:
            shown = ", ".join(p.get("name", p.get("sku", "")) for p in last_context[:3])
            return self._say({"text": s["no_discount"].format(q=shown), "citations": [{"type": "stock", "ref": p["sku"]} for p in last_context[:3] if p.get("sku")]})
        # offers / greeting
        if offers and (GREETING_RE.search(low) or not text):
            o = offers[0]
            return self._say({"text": o["text"], "buttons": [{"id": f"add:{o.get('sku')}", "label": lab["add"]}, {"id": "no", "label": lab["no"]}, {"id": "stop", "label": lab["stop"]}], "citations": [{"type": "play", "ref": o["play_id"]}]})
        if GREETING_RE.search(low) or not text:
            return self._say({"text": s["greet"].format(name=name)})
        return self._say({"text": s["unknown"]})
