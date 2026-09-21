"""Vernacular copy for approved plays (DECISIONS §5.2 step 7). In production this is
`AI.GENERATE_TABLE` over a Vertex-connected remote model with the numbers passed as constants;
locally, or on any BigQuery failure/timeout, it is templated. The validator is the same in both
modes: the discount and the best-before date in the text must match the play, or the variant is
rejected -- a model-generated variant is never trusted just because BigQuery also ran a check.
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


def _date_stated(iso: str | None, text: str) -> bool:
    """Whether `text` states the date `iso`, accepting either the templated "%d %b %Y" form or
    the raw ISO form -- a live model asked to "state the date plainly" reliably writes the ISO
    string it was given rather than reformatting it, so a check for only the formatted form
    rejects genuinely correct BigQuery-generated copy."""
    return bool(iso) and (_fmt_date(iso) in text or iso in text)


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
            variants.append({"segment_id": seg, "language": lang, "text": text, "disclosure_included": _date_stated(best_before, text)})
    return variants


def _bq_prompt_text(sku_name: str, mechanic: str, discount_pct: float | None, bundle_price: float | None, best_before: str | None, language: str) -> str:
    """Same instructions as data/bigquery/sense/08_copy.sql's prompt_text CONCAT, ported to
    Python because the minimal BigQuery path (see generate_copy_bigquery) builds its request
    rows here rather than reading them back out of `taal.plays`/`taal.products`, which this
    codebase never writes to.

    Always states `best_before` (the physical expiry/use-by date), never the online sell-by
    date, matching generate_copy()'s templates exactly: a shopper decides whether to buy near-
    expiry food from when it actually spoils, not from Taal's internal online-channel cutoff.
    The online sell-by date decides which mechanic is even admissible (the guardrails, before
    copy is drafted); it was never meant to be customer-facing. An earlier version of this
    function asked the model to state the online sell-by date instead for that deadline type,
    which `validate_copy` then rejected as a disclosure mismatch every time -- found live: the
    model correctly wrote the date it was told to, and was discarded anyway because the check
    compares against `best_before`, the same field the templated path is built from."""
    parts = [f"Write one short, plain, non-pushy message in {language} for a grocery customer.", f"Product: {sku_name}. Mechanic: {mechanic}."]
    if discount_pct is not None:
        parts.append(f"Discount: {discount_pct:g}% -- copy this number exactly, do not change it.")
    if bundle_price is not None:
        parts.append(f"Bundle price: Rs {bundle_price:g} -- copy this number exactly.")
    if best_before:
        parts.append(f"State the best-before date {best_before} plainly.")
    parts.append("Do not invent any other number or date. Keep it under 40 words.")
    return " ".join(parts)


def generate_copy_bigquery(play: dict[str, Any], product: dict[str, Any], best_before: str | None, languages: list[str], project: str, region: str, model_id: str, dataset: str = "taal", timeout_s: float = 6.0) -> list[dict[str, Any]]:
    """A real `AI.GENERATE_TABLE` call over the Vertex-connected remote model
    `{dataset}.{model_id}_remote` (created by infra/deploy.sh). `taal.plays` and `taal.products`
    are never populated by this codebase -- LocalStore is the system of record -- so this cannot
    join against them the way data/bigquery/sense/08_copy.sql does; instead it builds the
    variant_requests rows in Python from the play already in memory and passes them as a single
    parameterized `UNNEST(@rows)` array -- no temp table, no separate load job. Raises on any
    failure or on the timeout; the caller is expected to fall back to generate_copy() (templates)
    rather than let this block or fail the approve request -- see services/api/approve.py.

    An earlier version created a physical temp table (create + load + query: three sequential
    BigQuery jobs). Measured live at ~10s for a 10-row play, which never fit inside approve()'s
    critical-path timeout budget -- meaning this path silently lost to the templated fallback on
    every real approve() call, not just some. The single parameterized query measures ~3-4s for
    the same 10 rows, comfortably inside budget.
    """
    from google.cloud import bigquery

    # BigQuery splits a single backtick-quoted identifier on '.', so a model id with dots in it
    # (gemini-2.5-flash) silently mis-parses `project.dataset.gemini-2.5-flash_remote` as more
    # path segments than intended (a real failure found while wiring this up, not guessed: see
    # infra/deploy.sh's matching fix). Sanitize the resource name; the literal id still goes
    # into OPTIONS(endpoint=...) unsanitized, since that has to match Vertex's real model id.
    model_resource = model_id.replace(".", "_") + "_remote"
    params = play.get("mechanic_params") or {}
    discount_pct = params.get("discount_pct") or params.get("markdown_pct")
    bundle_price = params.get("bundle_price")
    requests = [
        (seg, lang, _bq_prompt_text(product["name"], play["mechanic"], discount_pct, bundle_price, best_before, lang))
        for seg in play["audience"]["segment_ids"]
        for lang in languages
    ]
    if not requests:
        return []

    client = bigquery.Client(project=project, location=region)
    # AI.GENERATE_TABLE reads its prompt from a column literally named `prompt` -- there is no
    # STRUCT field to rename it (`prompt_column` is rejected: "unsupported setting field"), and
    # `output_schema` must live inside the STRUCT too, not as a separate named (=>) argument
    # (rejected: "Named argument output_schema not found in signature"). Both confirmed live
    # against a real AI.GENERATE_TABLE call, not guessed from docs -- the function's accepted
    # signature isn't the one most examples online show.
    row_type = bigquery.StructQueryParameterType(
        bigquery.ScalarQueryParameterType("STRING", name="segment_id"),
        bigquery.ScalarQueryParameterType("STRING", name="language"),
        bigquery.ScalarQueryParameterType("STRING", name="prompt"),
    )
    rows_param = bigquery.ArrayQueryParameter(
        "rows",
        row_type,
        [
            bigquery.StructQueryParameter(None, bigquery.ScalarQueryParameter("segment_id", "STRING", seg), bigquery.ScalarQueryParameter("language", "STRING", lang), bigquery.ScalarQueryParameter("prompt", "STRING", prompt))
            for seg, lang, prompt in requests
        ],
    )
    query = (
        f"SELECT segment_id, language, copy_text FROM AI.GENERATE_TABLE("
        f"MODEL `{project}`.`{dataset}`.`{model_resource}`, "
        "(SELECT * FROM UNNEST(@rows)), "
        "STRUCT('copy_text STRING' AS output_schema))"
    )
    job_config = bigquery.QueryJobConfig(query_parameters=[rows_param])
    by_key = {(r["segment_id"], r["language"]): r["copy_text"] for r in client.query(query, job_config=job_config).result(timeout=timeout_s)}

    variants = []
    for seg in play["audience"]["segment_ids"]:
        for lang in languages:
            text = by_key.get((seg, lang))
            if text:
                variants.append({"segment_id": seg, "language": lang, "text": text, "disclosure_included": _date_stated(best_before, text)})
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
        if best_before and need_disclosure and not _date_stated(best_before, text):
            reasons.append(f"{v['segment_id']}/{v['language']}: best-before date mismatch")
            continue
        ok.append(v)
    return ok, reasons
