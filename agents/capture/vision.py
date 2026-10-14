"""Vision intake (DECISIONS §5.1): a pallet photo -> batch rows with dates, counts and confidence.

`vertex` backend: one Gemini call with the output schema (docs/schemas/vision_intake.schema.json);
a second pass on a cropped label region when any date confidence is below the threshold.
`stub` backend: the recorded rows under fixtures/photos/pallet_0N.json for each staged photo;
an uploaded photo (data URL) gets two low-confidence rows so the confirmation flow is exercised.
Rows below the threshold always carry a confirmation question; nothing is written to inventory
until `commit_rows` receives the confirmed rows.
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
from datetime import date
from typing import Any

import jsonschema

from agents.gate.config import ROOT, load_models, load_tenant
from agents.gate.sellby import online_sellby_date
from agents.gate.store import LocalStore
from agents.vertex_models import generate_with_failover

CONFIDENCE_THRESHOLD = 0.7
SCHEMA = json.loads((ROOT / "docs" / "schemas" / "vision_intake.schema.json").read_text(encoding="utf-8"))
_VALIDATOR = jsonschema.Draft202012Validator(SCHEMA, format_checker=jsonschema.FormatChecker())
FIXTURES = ROOT / "fixtures" / "photos"
LOG = logging.getLogger(__name__)
# V3 (adversarial eval, 14 Oct 2026). Largest facings count in any recorded read: 6 over the 30 synthetic
# photos (true max 5), 4 on the staged pallets and 24 on the low-confidence test fixture
# (fixtures/photos/pallet_lowconf_test.json); 60 is 2.5x the largest of those and far below the 240-500
# a photographed stock table produced. Above it a human confirms, nothing is auto-accepted.
MAX_PLAUSIBLE_FACINGS = 60
SKU_CONFIDENCE_FLOOR = 0.3

PROMPT = (
    "You are reading a retail pallet or shelf photo for a grocery dark store in Bengaluru. For every distinct "
    "product facing block, return the SKU you believe it is (choose from the catalogue below), the printed best-before "
    "date as YYYY-MM-DD or null, the number of facings you can count, and a 0-1 confidence for each of the three. "
    "Never guess a date you cannot read; set it to null with a low confidence instead."
)


def _question(row: dict[str, Any], names: dict[str, str]) -> str:
    name = names.get(row["sku_guess"], row["sku_guess"])
    bb = row.get("best_before_date")
    when = f"best before {date.fromisoformat(bb).strftime('%d %b %Y')}" if bb else "best-before date unreadable"
    return f"Is this {name}, {when}, {row['facings_count']} facings?"


def annotate(result: dict[str, Any], names: dict[str, str], threshold: float = CONFIDENCE_THRESHOLD) -> dict[str, Any]:
    for row in result["rows"]:
        low = min(row["sku_confidence"], row["date_confidence"], row["count_confidence"]) < threshold or row.get("best_before_date") is None
        row["needs_confirmation"] = bool(low)
        if low:
            row["confirmation_question"] = _question(row, names)
        else:
            row.pop("confirmation_question", None)
    result["pass"] = "two_pass" if any(r["date_confidence"] < threshold for r in result["rows"]) else "single"
    _VALIDATOR.validate(result)
    return result


def drop_unknown_skus(result: dict[str, Any], names: dict[str, str]) -> list[str]:
    """V6: a row whose SKU is not in the catalogue given to intake is a model invention. It cannot be
    confirmed into stock (commit_rows skips unknown SKUs anyway), so it is dropped from the result and
    logged rather than shown as a real product; the output schema is closed, so no extra field can
    carry the reason. Limit, stated plainly: the recorded V6 invention (SKU-MILK-BREAD-400G) is a REAL
    catalogue SKU (every SKU is stocked at every node in the seeded tenant, so a per-node list adds
    nothing). Code cannot know what is in the photo, so that row is not dropped: it stays flagged
    (sku_confidence 0.4 < 0.7, date null) and cannot reach inventory unconfirmed.
    Returns the dropped SKUs."""
    kept, dropped = [], []
    for r in result["rows"]:
        (kept if r["sku_guess"] in names else dropped).append(r)
    if dropped:
        LOG.warning("vision: dropped rows with SKUs outside the catalogue: %s", [r["sku_guess"] for r in dropped])
    result["rows"] = kept
    return [r["sku_guess"] for r in dropped]


def flag_implausible(result: dict[str, Any], names: dict[str, str]) -> None:
    """V3 and V6: deterministic plausibility gate on a LIVE read, applied after `annotate`. Forces
    needs_confirmation (with the reason in the confirmation question) for: a facings count above
    MAX_PLAUSIBLE_FACINGS; sku_confidence below SKU_CONFIDENCE_FLOOR; and a read in which every
    confidence of every row is exactly 1.0 (a photographed screen or a printed claim of certainty;
    real reads of real photos give 0.9-0.99, see eval/raw/adversarial_2026-10-14 VC1/VC2). Never
    un-flags a row; the model prompt and schema are untouched."""
    rows = result["rows"]
    all_certain = bool(rows) and all(r[k] == 1.0 for r in rows for k in ("sku_confidence", "date_confidence", "count_confidence"))
    for r in rows:
        why = []
        if int(r["facings_count"]) > MAX_PLAUSIBLE_FACINGS:
            why.append(f"{r['facings_count']} facings is implausible (more than {MAX_PLAUSIBLE_FACINGS})")
        if r["sku_confidence"] < SKU_CONFIDENCE_FLOOR:
            why.append("SKU is a weak guess")
        if all_certain:
            why.append("every confidence is exactly 1.0, which a real read does not give")
        if why:
            r["needs_confirmation"] = True
            r["confirmation_question"] = _question(r, names) + " Check: " + "; ".join(why) + "."
    _VALIDATOR.validate(result)


def _stub_rows(photo_ref: str | None, image_data_url: str | None, node_id: str) -> dict[str, Any]:
    if photo_ref:
        name = photo_ref.rsplit("/", 1)[-1].rsplit(".", 1)[0]
        f = FIXTURES / f"{name}.json"
        if f.exists():
            d = json.loads(f.read_text(encoding="utf-8"))
            return {"photo_ref": photo_ref, "node_id": node_id, "rows": d["rows"]}
    digest = hashlib.sha256((image_data_url or photo_ref or "").encode()).hexdigest()[:8]
    return {"photo_ref": photo_ref or f"upload:{digest}", "node_id": node_id, "rows": [
        {"sku_guess": "SKU-MASALA-CHIPS-200G", "sku_confidence": 0.62, "best_before_date": None, "date_confidence": 0.40, "facings_count": 8, "count_confidence": 0.55},
        {"sku_guess": "SKU-COLA-LITE-500ML", "sku_confidence": 0.58, "best_before_date": None, "date_confidence": 0.35, "facings_count": 6, "count_confidence": 0.50},
    ]}


# Gemini's response_schema is not JSON Schema: one type per field (no ["string", "null"] unions),
# nullability via `nullable`, and no `format`/`minimum`/`additionalProperties`. Reusing
# docs/schemas/vision_intake.schema.json directly fails validation inside google-genai before any
# model call is made; the output is still validated against the JSON Schema in `annotate`.
_CONF = {"type": "NUMBER"}
_GEMINI_ROWS_SCHEMA = {
    "type": "OBJECT",
    "required": ["rows"],
    "properties": {"rows": {"type": "ARRAY", "items": {
        "type": "OBJECT",
        "required": ["sku_guess", "sku_confidence", "best_before_date", "date_confidence", "facings_count", "count_confidence"],
        "properties": {
            "sku_guess": {"type": "STRING"},
            "sku_confidence": _CONF,
            "best_before_date": {"type": "STRING", "nullable": True, "description": "YYYY-MM-DD, or null when unreadable"},
            "date_confidence": _CONF,
            "facings_count": {"type": "INTEGER"},
            "count_confidence": _CONF,
        },
    }}},
}


def _is_remote_uri(ref: str | None) -> bool:
    return bool(ref) and ref.startswith(("gs://", "https://", "http://"))


def _vertex_rows(photo_ref: str | None, image_data_url: str | None, node_id: str, catalogue: list[str], models: dict[str, Any]) -> dict[str, Any]:
    """One Gemini read of the photo (plus a second pass on unreadable dates). The primary model
    answers; on an availability error (404, 429, 5xx) the call is retried on `ids.fallback`
    (agents/vertex_models.py), and the result's `model_id` is the model that actually answered.
    Raises ModelUnavailable when both fail."""
    from google.genai import types

    schema = _GEMINI_ROWS_SCHEMA
    if image_data_url:
        header, b64 = image_data_url.split(",", 1)
        mime = header.split(";")[0].split(":")[1]
        part = types.Part.from_bytes(data=base64.b64decode(b64), mime_type=mime)
    elif _is_remote_uri(photo_ref):
        part = types.Part.from_uri(file_uri=photo_ref, mime_type="image/jpeg")
    else:
        raise ValueError(f"vertex vision needs an uploaded image or a gs://, https:// photo_ref; got {photo_ref!r}")
    prompt = PROMPT + "\nCatalogue SKUs: " + ", ".join(catalogue[:400])
    config = types.GenerateContentConfig(response_mime_type="application/json", response_schema=schema, temperature=0.0)
    level = models.get("thinking", {}).get("vision")  # optional; absent keeps the model's default
    resp, used = generate_with_failover(models, [part, prompt], config, thinking_level=level)
    rows = json.loads(resp.text)["rows"]
    if any(r["date_confidence"] < CONFIDENCE_THRESHOLD for r in rows):
        second, used = generate_with_failover(models, [part, prompt + "\nSecond pass: look only at the printed date labels, one per block, and re-read the dates."], config, start=used, thinking_level=level)
        by_sku = {r["sku_guess"]: r for r in json.loads(second.text)["rows"]}
        for r in rows:
            s = by_sku.get(r["sku_guess"])
            if s and s["date_confidence"] > r["date_confidence"]:
                r["best_before_date"], r["date_confidence"] = s["best_before_date"], s["date_confidence"]
    return {"photo_ref": photo_ref or "upload", "node_id": node_id, "rows": rows, "model_id": used}


def intake(store: LocalStore, node_id: str, photo_ref: str | None = None, image_data_url: str | None = None, backend: str | None = None) -> dict[str, Any]:
    models = load_models()
    backend = backend or models["backend"]
    products = store.read("products")
    names = {p["sku"]: p["name"] for p in products}
    recorded = photo_ref and not image_data_url and (FIXTURES / f"{photo_ref.rsplit('/', 1)[-1].rsplit('.', 1)[0]}.json").exists()
    if backend == "vertex" and not recorded:
        result = _vertex_rows(photo_ref, image_data_url, node_id, sorted(names), models)
        drop_unknown_skus(result, names)
        annotate(result, names)
        flag_implausible(result, names)
        return result
    elif backend == "vertex":
        # The three staged pallets have no image file in the repo, only their recorded Gemini reads
        # (fixtures/photos/README.md); the phone view labels them REPLAY. Only a real upload is live.
        result = _stub_rows(photo_ref, image_data_url, node_id)
        result["model_id"] = "recorded"
    else:
        result = _stub_rows(photo_ref, image_data_url, node_id)
        result["model_id"] = "stub-vision"
    return annotate(result, names)


def commit_rows(store: LocalStore, node_id: str, rows: list[dict[str, Any]], photo_ref: str, received_at: str) -> dict[str, list[dict[str, Any]]]:
    """Confirmed rows -> inventory_batches (source=photo). Returns {"written": [...], "skipped": [...]}
    -- a row that needs but lacks confirmation, names an unknown SKU, or has no best_before_date
    (the exact case the confirmation flow exists to let an operator fill in) is skipped with a
    reason, never silently dropped: a caller must be able to tell 'nothing to write' from 'wrote
    everything'."""
    tenant = load_tenant()
    products = {p["sku"]: p for p in store.read("products")}
    written, skipped = [], []
    for i, r in enumerate(rows, start=1):
        sku_guess = r.get("sku_guess")
        if r.get("needs_confirmation") and not r.get("confirmed"):
            skipped.append({"sku_guess": sku_guess, "reason": "not confirmed"})
            continue
        p = products.get(sku_guess)
        if not p:
            skipped.append({"sku_guess": sku_guess, "reason": "unknown SKU"})
            continue
        if not r.get("best_before_date"):
            skipped.append({"sku_guess": sku_guess, "reason": "no best_before_date"})
            continue
        expiry = date.fromisoformat(r["best_before_date"])
        batch_id = f"B-PHOTO-{hashlib.sha256(f'{photo_ref}|{node_id}|{i}'.encode()).hexdigest()[:6].upper()}"
        written.append({
            "tenant_id": tenant.tenant_id, "batch_id": batch_id, "sku": sku_guess, "node_id": node_id, "qty_on_hand": int(r["facings_count"]),
            "expiry_date": expiry.isoformat(), "online_sellby_date": online_sellby_date(expiry, int(p["shelf_life_days"]), tenant.sellby_rule, bool(p["is_food"])).isoformat(),
            "received_at": received_at[:10], "source": "photo", "capture_ref": photo_ref, "sellby_rule_version": tenant.sellby_rule.version,
        })
    if written:
        store.append("inventory_batches", written)
    return {"written": written, "skipped": skipped}


def _env_backend() -> str:
    return os.environ.get("TAAL_MODEL_BACKEND", "stub")
