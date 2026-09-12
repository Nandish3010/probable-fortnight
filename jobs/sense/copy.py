"""Vernacular copy for approved plays (DECISIONS §5.2 step 7). In production this is
`AI.GENERATE_TABLE` over a Vertex-connected Flash-Lite model with the numbers passed as
constants; locally it is templated. The validator is the same in both modes: the discount and
the best-before date in the text must match the play, or the variant is rejected.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Any

TEMPLATES = {
    "en": {
        "bundle": "{name}: buy with {partner} for ₹{bundle_price} today at your Kutumb Mart store. Best before {best_before}.",
        "coupon": "{name}: {discount_pct}% off today at your Kutumb Mart store. Best before {best_before}.",
        "usual_order_addon": "Add {name} to your usual order this week. Best before {best_before}.",
        "substitution": "{name} is back in stock at your store. Best before {best_before}.",
        "preorder": "{name} is arriving on {eta}. Reserve yours now.",
        "subscription_nudge": "Your {name} subscription can be delivered early this week.",
        "outlet_markdown": "{name}: {markdown_pct}% off in store this week. Best before {best_before}.",
        "transfer_plus_nudge": "{name} is now available at your nearest Kutumb Mart outlet. Best before {best_before}.",
    },
    "kn": {
        "bundle": "{name}: ಇಂದು {partner} ಜೊತೆ ₹{bundle_price}ಕ್ಕೆ ನಿಮ್ಮ ಕುಟುಂಬ ಮಾರ್ಟ್‌ನಲ್ಲಿ. ಬಳಕೆಗೆ ಉತ್ತಮ {best_before}ರವರೆಗೆ.",
        "coupon": "{name}: ಇಂದು {discount_pct}% ರಿಯಾಯಿತಿ ನಿಮ್ಮ ಕುಟುಂಬ ಮಾರ್ಟ್‌ನಲ್ಲಿ. ಬಳಕೆಗೆ ಉತ್ತಮ {best_before}ರವರೆಗೆ.",
        "usual_order_addon": "ಈ ವಾರ ನಿಮ್ಮ ಸಾಮಾನ್ಯ ಆರ್ಡರ್‌ಗೆ {name} ಸೇರಿಸಿ. ಬಳಕೆಗೆ ಉತ್ತಮ {best_before}ರವರೆಗೆ.",
        "substitution": "{name} ನಿಮ್ಮ ಸ್ಟೋರ್‌ನಲ್ಲಿ ಮತ್ತೆ ಲಭ್ಯ. ಬಳಕೆಗೆ ಉತ್ತಮ {best_before}ರವರೆಗೆ.",
        "preorder": "{name} {eta}ರಂದು ಬರುತ್ತಿದೆ. ಈಗಲೇ ಕಾಯ್ದಿರಿಸಿ.",
        "subscription_nudge": "ನಿಮ್ಮ {name} ಚಂದಾದಾರಿಕೆ ಈ ವಾರ ಬೇಗ ತಲುಪಿಸಬಹುದು.",
        "outlet_markdown": "{name}: ಈ ವಾರ ಅಂಗಡಿಯಲ್ಲಿ {markdown_pct}% ರಿಯಾಯಿತಿ. ಬಳಕೆಗೆ ಉತ್ತಮ {best_before}ರವರೆಗೆ.",
        "transfer_plus_nudge": "{name} ಈಗ ನಿಮ್ಮ ಹತ್ತಿರದ ಕುಟುಂಬ ಮಾರ್ಟ್ ಔಟ್‌ಲೆಟ್‌ನಲ್ಲಿ ಲಭ್ಯ. ಬಳಕೆಗೆ ಉತ್ತಮ {best_before}ರವರೆಗೆ.",
    },
}
NEAR_DEADLINE = {"clear_online_sellby", "clear_expiry"}


def _fmt_date(iso: str | None) -> str:
    if not iso:
        return "-"
    d = date.fromisoformat(iso)
    return d.strftime("%d %b %Y")


def generate_copy(play: dict[str, Any], product: dict[str, Any], partner: dict[str, Any] | None, best_before: str | None, languages: list[str]) -> list[dict[str, Any]]:
    params = play.get("mechanic_params") or {}
    ctx = {
        "name": product["name"], "partner": (partner or {}).get("name", ""), "bundle_price": f"{float(params.get('bundle_price') or 0):g}",
        "discount_pct": f"{float(params.get('discount_pct') or 0):g}", "markdown_pct": f"{float(params.get('markdown_pct') or 0):g}",
        "eta": _fmt_date(params.get("preorder_eta_date")), "best_before": _fmt_date(best_before),
    }
    variants = []
    for seg in play["audience"]["segment_ids"]:
        for lang in languages:
            tpl = TEMPLATES.get(lang, TEMPLATES["en"]).get(play["mechanic"], TEMPLATES["en"]["usual_order_addon"])
            text = tpl.format(**ctx)
            variants.append({"segment_id": seg, "language": lang, "text": text, "disclosure_included": ctx["best_before"] in text and best_before is not None})
    return variants


def validate_copy(variants: list[dict[str, Any]], play: dict[str, Any], best_before: str | None) -> tuple[list[dict[str, Any]], list[str]]:
    """Reject a variant whose numbers disagree with the play or which omits the best-before line
    on a near-deadline play. Returns (accepted, reasons)."""
    params = play.get("mechanic_params") or {}
    ok, reasons = [], []
    need_disclosure = play.get("objective") in NEAR_DEADLINE
    for v in variants:
        text = v["text"]
        pct = params.get("discount_pct") or params.get("markdown_pct")
        if pct is not None and "%" in text:
            found = [float(x) for x in re.findall(r"(\d+(?:\.\d+)?)%", text)]
            if found and all(abs(f - float(pct)) > 0.01 for f in found):
                reasons.append(f"{v['segment_id']}/{v['language']}: discount {found} != {pct}")
                continue
        if need_disclosure and not v.get("disclosure_included"):
            reasons.append(f"{v['segment_id']}/{v['language']}: best-before missing")
            continue
        if best_before and need_disclosure and _fmt_date(best_before) not in text:
            reasons.append(f"{v['segment_id']}/{v['language']}: best-before date mismatch")
            continue
        ok.append(v)
    return ok, reasons
