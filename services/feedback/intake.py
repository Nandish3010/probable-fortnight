"""Turn one raw POST /feedback body into a stored record, or refuse it.

Order matters: size cap first (before any parsing), then the honeypot (before validation, so a
bot filling every field gets the same 200 whether or not the rest of its payload is valid), then
the JSON Schema -- the source of truth, including the show-if rules -- and finally the Pydantic
mirror as a second check.
"""
from __future__ import annotations

import json
import re
import secrets
from datetime import datetime
from functools import cache
from pathlib import Path
from typing import Any

import jsonschema
from pydantic import ValidationError

from .models import FeedbackSubmission

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "docs" / "schemas" / "feedback_response.schema.json"
FORM_PATH = ROOT / "config" / "feedback_form.json"
RESPONSE_ID_RE = re.compile(r"^[0-9a-f]{32}$")
MAX_BODY_BYTES = 16_384  # the largest valid submission is ~3.5 KB of text; four times that is plenty


class Rejected(Exception):
    def __init__(self, status: int, detail: Any):
        super().__init__(str(detail))
        self.status, self.detail = status, detail


@cache
def schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


@cache
def form() -> dict[str, Any]:
    return json.loads(FORM_PATH.read_text(encoding="utf-8"))


@cache
def _validator() -> jsonschema.Draft202012Validator:
    return jsonschema.Draft202012Validator(schema(), format_checker=jsonschema.FormatChecker())


def new_response_id() -> str:
    """128 random bits, hex. Server-assigned so a client can never pick (and so overwrite or
    probe for) another respondent's id; it doubles as the reference a respondent quotes to ask
    for deletion."""
    return secrets.token_hex(16)


def parse(raw: bytes) -> dict[str, Any] | None:
    """Return the validated submission, None for a honeypot hit (to be discarded silently), or
    raise Rejected."""
    if len(raw) > MAX_BODY_BYTES:
        raise Rejected(413, f"request body over {MAX_BODY_BYTES} bytes")
    try:
        doc = json.loads(raw)
    except (ValueError, UnicodeDecodeError) as e:
        raise Rejected(422, f"body is not valid JSON: {e}") from e
    if isinstance(doc, dict) and isinstance(doc.get("website"), str) and doc["website"].strip():
        return None
    errors = sorted(_validator().iter_errors(doc), key=lambda e: list(e.absolute_path))
    if errors:
        raise Rejected(422, [{"loc": ["body", *e.absolute_path], "msg": e.message} for e in errors[:20]])
    try:
        FeedbackSubmission.model_validate(doc)
    except ValidationError as e:  # the schema passed but the mirror did not: drift, still a 422
        raise Rejected(422, [{"loc": ["body", *err["loc"]], "msg": err["msg"]} for err in e.errors()[:20]]) from e
    return doc


def to_record(doc: dict[str, Any], response_id: str, submitted_at: datetime) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Split a validated submission into (answers record, contact or None)."""
    answers = dict(doc["answers"])
    contact_fields = answers.pop("e3_contact", None)
    ts = submitted_at.isoformat(timespec="seconds").replace("+00:00", "Z")
    record = {
        "response_id": response_id, "submitted_at": ts, "form_version": doc["form_version"],
        "mode": doc["mode"], "source": doc["source"], "answers": answers, "has_contact": bool(contact_fields),
    }
    contact = {"response_id": response_id, "submitted_at": ts, **contact_fields} if contact_fields else None
    return record, contact
