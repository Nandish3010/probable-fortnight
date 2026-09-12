"""Vision intake (DECISIONS §5.1): a pallet photo -> batch rows with dates, counts and confidence.

`vertex` backend: one Gemini call with the output schema (docs/schemas/vision_intake.schema.json);
a second pass on a cropped label region when any date confidence is below the threshold.
`stub` backend: the recorded rows under fixtures/photos/pallet_0N.json for the three staged photos;
an uploaded photo (data URL) gets two low-confidence rows so the confirmation flow is exercised.
Rows below the threshold always carry a confirmation question; nothing is written to inventory
until `commit_rows` receives the confirmed rows.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
from datetime import date
from typing import Any

import jsonschema

from agents.gate.config import ROOT, load_models, load_tenant
from agents.gate.sellby import online_sellby_date
from agents.gate.store import LocalStore

CONFIDENCE_THRESHOLD = 0.7
SCHEMA = json.loads((ROOT / "docs" / "schemas" / "vision_intake.schema.json").read_text(encoding="utf-8"))
_VALIDATOR = jsonschema.Draft202012Validator(SCHEMA, format_checker=jsonschema.FormatChecker())
FIXTURES = ROOT / "fixtures" / "photos"

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


def _vertex_rows(photo_ref: str | None, image_data_url: str | None, node_id: str, catalogue: list[str], model_id: str) -> dict[str, Any]:
    from google import genai
    from google.genai import types

    client = genai.Client(vertexai=True)
    schema = {"type": "object", "properties": {"rows": SCHEMA["properties"]["rows"]}, "required": ["rows"]}
    if image_data_url:
        header, b64 = image_data_url.split(",", 1)
        mime = header.split(";")[0].split(":")[1]
        part = types.Part.from_bytes(data=base64.b64decode(b64), mime_type=mime)
    else:
        part = types.Part.from_uri(file_uri=photo_ref, mime_type="image/jpeg")
    prompt = PROMPT + "\nCatalogue SKUs: " + ", ".join(catalogue[:400])
    resp = client.models.generate_content(model=model_id, contents=[part, prompt], config=types.GenerateContentConfig(response_mime_type="application/json", response_schema=schema, temperature=0.0))
    rows = json.loads(resp.text)["rows"]
    if any(r["date_confidence"] < CONFIDENCE_THRESHOLD for r in rows):
        second = client.models.generate_content(model=model_id, contents=[part, prompt + "\nSecond pass: look only at the printed date labels, one per block, and re-read the dates."], config=types.GenerateContentConfig(response_mime_type="application/json", response_schema=schema, temperature=0.0))
        by_sku = {r["sku_guess"]: r for r in json.loads(second.text)["rows"]}
        for r in rows:
            s = by_sku.get(r["sku_guess"])
            if s and s["date_confidence"] > r["date_confidence"]:
                r["best_before_date"], r["date_confidence"] = s["best_before_date"], s["date_confidence"]
    return {"photo_ref": photo_ref or "upload", "node_id": node_id, "rows": rows}


def intake(store: LocalStore, node_id: str, photo_ref: str | None = None, image_data_url: str | None = None, backend: str | None = None) -> dict[str, Any]:
    models = load_models()
    backend = backend or models["backend"]
    products = store.read("products")
    names = {p["sku"]: p["name"] for p in products}
    if backend == "vertex":
        result = _vertex_rows(photo_ref, image_data_url, node_id, sorted(names), models["ids"]["flash"])
        result["model_id"] = models["ids"]["flash"]
    else:
        result = _stub_rows(photo_ref, image_data_url, node_id)
        result["model_id"] = "stub-vision"
    return annotate(result, names)


def commit_rows(store: LocalStore, node_id: str, rows: list[dict[str, Any]], photo_ref: str, received_at: str) -> list[dict[str, Any]]:
    """Confirmed rows -> inventory_batches (source=photo). Unconfirmed low-confidence rows are refused."""
    tenant = load_tenant()
    products = {p["sku"]: p for p in store.read("products")}
    out = []
    for i, r in enumerate(rows, start=1):
        if r.get("needs_confirmation") and not r.get("confirmed"):
            continue
        p = products.get(r["sku_guess"])
        if not p or not r.get("best_before_date"):
            continue
        expiry = date.fromisoformat(r["best_before_date"])
        batch_id = f"B-PHOTO-{hashlib.sha256(f'{photo_ref}|{node_id}|{i}'.encode()).hexdigest()[:6].upper()}"
        out.append({
            "tenant_id": tenant.tenant_id, "batch_id": batch_id, "sku": r["sku_guess"], "node_id": node_id, "qty_on_hand": int(r["facings_count"]),
            "expiry_date": expiry.isoformat(), "online_sellby_date": online_sellby_date(expiry, int(p["shelf_life_days"]), tenant.sellby_rule, bool(p["is_food"])).isoformat(),
            "received_at": received_at[:10], "source": "photo", "capture_ref": photo_ref, "sellby_rule_version": tenant.sellby_rule.version,
        })
    if out:
        store.append("inventory_batches", out)
    return out


def _env_backend() -> str:
    return os.environ.get("TAAL_MODEL_BACKEND", "stub")
