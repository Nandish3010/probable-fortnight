"""Reading a garment photo or a selfie into attributes (DECISIONS §5.9). Same pattern as
agents/capture/vision.py: a strict output schema, a stub backend that returns recorded attributes
for staged fixtures, a Gemini backend for `vertex` mode. `colour_family` is always resolved
deterministically (agents/stylist/colour.py::family_of), never a model output.

Nothing in this module writes to a store or the filesystem, and nothing here keeps the image bytes
beyond the call: a selfie is read once, in memory, and discarded. `photo_ref` in every return value
is either the fixture name or an 8-character digest of the uploaded bytes -- never the image data
itself -- so it is safe to put into `tool_calls` and the conversation trace.
"""
from __future__ import annotations

import base64
import hashlib
import json
from typing import Any

import jsonschema

from agents.gate.config import ROOT, load_models

from .colour import family_of
from .parse import ParsedGarment

CONFIDENCE_THRESHOLD = 0.7
GARMENT_SCHEMA = json.loads((ROOT / "docs" / "schemas" / "stylist_garment.schema.json").read_text(encoding="utf-8"))
SKIN_TONE_SCHEMA = json.loads((ROOT / "docs" / "schemas" / "stylist_skin_tone.schema.json").read_text(encoding="utf-8"))
_GARMENT_VALIDATOR = jsonschema.Draft202012Validator(GARMENT_SCHEMA, format_checker=jsonschema.FormatChecker())
_SKIN_TONE_VALIDATOR = jsonschema.Draft202012Validator(SKIN_TONE_SCHEMA, format_checker=jsonschema.FormatChecker())
GARMENT_FIXTURES = ROOT / "fixtures" / "photos" / "garments"
SELFIE_FIXTURES = ROOT / "fixtures" / "photos" / "selfies"

GARMENT_PROMPT = "You are reading a photo of a single garment for a fashion stylist chat. Return the garment type, the dominant colour word, and the pattern (solid unless clearly patterned), each with a 0-1 confidence. Never guess a garment type you cannot see; return null with a low confidence instead."
SKIN_TONE_PROMPT = "You are reading a selfie only to estimate two coarse attributes for clothing colour suggestions: skin undertone (warm, cool, or neutral) and depth (light, medium, or deep). Return null for both if no face is clearly visible. Do not describe the person in any other way."


def _fixture_stem(photo_ref: str | None) -> str | None:
    if not photo_ref:
        return None
    return photo_ref.rsplit("/", 1)[-1].rsplit(".", 1)[0]


def _decoded_bytes(image_data_url: str) -> bytes:
    _, b64 = image_data_url.split(",", 1) if "," in image_data_url else ("", image_data_url)
    try:
        return base64.b64decode(b64)
    except Exception:
        return image_data_url.encode()


def _digest(image_data_url: str) -> str:
    return hashlib.sha256(_decoded_bytes(image_data_url)).hexdigest()[:8]


def _stub_garment(photo_ref: str | None, image_data_url: str | None) -> dict[str, Any]:
    stem = _fixture_stem(photo_ref)
    if stem:
        f = GARMENT_FIXTURES / f"{stem}.json"
        if f.exists():
            attrs = json.loads(f.read_text(encoding="utf-8"))
            return {"photo_ref": photo_ref, **attrs}
    if image_data_url:
        digest = _digest(image_data_url)
        for f in GARMENT_FIXTURES.glob("*.png"):
            if digest == hashlib.sha256(f.read_bytes()).hexdigest()[:8]:
                attrs = json.loads((GARMENT_FIXTURES / f"{f.stem}.json").read_text(encoding="utf-8"))
                return {"photo_ref": f"upload:{digest}", **attrs}
    ref = f"upload:{_digest(image_data_url)}" if image_data_url else (photo_ref or "upload:unknown")
    return {"photo_ref": ref, "garment_type": None, "colour": None, "pattern": None, "confidence": 0.25}


def _stub_skin_tone(photo_ref: str | None, image_data_url: str | None) -> dict[str, Any]:
    stem = _fixture_stem(photo_ref)
    if stem:
        f = SELFIE_FIXTURES / f"{stem}.json"
        if f.exists():
            attrs = json.loads(f.read_text(encoding="utf-8"))
            return {"photo_ref": photo_ref, **attrs}
    if image_data_url:
        digest = _digest(image_data_url)
        for f in SELFIE_FIXTURES.glob("*.png"):
            if digest == hashlib.sha256(f.read_bytes()).hexdigest()[:8]:
                attrs = json.loads((SELFIE_FIXTURES / f"{f.stem}.json").read_text(encoding="utf-8"))
                return {"photo_ref": f"upload:{digest}", **attrs}
    ref = f"upload:{_digest(image_data_url)}" if image_data_url else (photo_ref or "upload:unknown")
    return {"photo_ref": ref, "undertone": None, "depth": None, "confidence": 0.30}


def _image_part(image_data_url: str | None, photo_ref: str | None):
    from google.genai import types

    if image_data_url:
        header, b64 = image_data_url.split(",", 1)
        mime = header.split(";")[0].split(":")[1]
        return types.Part.from_bytes(data=base64.b64decode(b64), mime_type=mime)
    return types.Part.from_uri(file_uri=photo_ref, mime_type="image/jpeg")


def _vertex_garment(photo_ref: str | None, image_data_url: str | None, model_id: str) -> dict[str, Any]:
    from google import genai
    from google.genai import types

    client = genai.Client(vertexai=True)
    schema = {"type": "object", "properties": {"garment_type": {"type": ["string", "null"]}, "colour": {"type": ["string", "null"]}, "pattern": {"type": ["string", "null"]}, "confidence": {"type": "number"}}, "required": ["garment_type", "colour", "pattern", "confidence"]}
    part = _image_part(image_data_url, photo_ref)
    resp = client.models.generate_content(model=model_id, contents=[part, GARMENT_PROMPT], config=types.GenerateContentConfig(response_mime_type="application/json", response_schema=schema, temperature=0.0))
    attrs = json.loads(resp.text)
    return {"photo_ref": photo_ref or "upload", **attrs}


def _vertex_skin_tone(photo_ref: str | None, image_data_url: str | None, model_id: str) -> dict[str, Any]:
    from google import genai
    from google.genai import types

    client = genai.Client(vertexai=True)
    schema = {"type": "object", "properties": {"undertone": {"type": ["string", "null"]}, "depth": {"type": ["string", "null"]}, "confidence": {"type": "number"}}, "required": ["undertone", "depth", "confidence"]}
    part = _image_part(image_data_url, photo_ref)
    resp = client.models.generate_content(model=model_id, contents=[part, SKIN_TONE_PROMPT], config=types.GenerateContentConfig(response_mime_type="application/json", response_schema=schema, temperature=0.0))
    attrs = json.loads(resp.text)
    return {"photo_ref": photo_ref or "upload", **attrs}


def describe_garment_photo(image_data_url: str | None = None, photo_ref: str | None = None, backend: str | None = None) -> dict[str, Any]:
    models = load_models()
    backend = backend or models["backend"]
    if backend == "vertex":
        result = _vertex_garment(photo_ref, image_data_url, models["ids"]["flash"])
        result["model_id"] = models["ids"]["flash"]
    else:
        result = _stub_garment(photo_ref, image_data_url)
        result["model_id"] = "stub-vision"
    colour = result.pop("colour", None)
    colour_family = family_of(colour)
    garment_type = result.get("garment_type")
    pattern = result.get("pattern")
    confidence = float(result.get("confidence", 0.0))
    needs_confirmation = confidence < CONFIDENCE_THRESHOLD or garment_type is None
    description = ParsedGarment(garment_type=garment_type, colour=colour, colour_family=colour_family, pattern=pattern).describe() if garment_type else "a garment I could not identify"
    out = {"photo_ref": result["photo_ref"], "model_id": result["model_id"], "garment_type": garment_type, "colour": colour, "colour_family": colour_family, "pattern": pattern, "confidence": confidence, "needs_confirmation": needs_confirmation, "description": description}
    if result.get("fabric"):
        out["fabric"] = result["fabric"]
    _GARMENT_VALIDATOR.validate(out)
    return out


def read_skin_tone(image_data_url: str | None = None, photo_ref: str | None = None, backend: str | None = None) -> dict[str, Any]:
    models = load_models()
    backend = backend or models["backend"]
    if backend == "vertex":
        result = _vertex_skin_tone(photo_ref, image_data_url, models["ids"]["flash"])
        result["model_id"] = models["ids"]["flash"]
    else:
        result = _stub_skin_tone(photo_ref, image_data_url)
        result["model_id"] = "stub-vision"
    out = {"photo_ref": result["photo_ref"], "model_id": result["model_id"], "undertone": result.get("undertone"), "depth": result.get("depth"), "confidence": float(result.get("confidence", 0.0)), "needs_confirmation": True}
    _SKIN_TONE_VALIDATOR.validate(out)
    return out
