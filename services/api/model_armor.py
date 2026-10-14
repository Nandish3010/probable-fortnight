"""Model Armor screening for customer chat: the prompt before the agent sees it, the reply before
the customer does.

Off unless TAAL_MODEL_ARMOR_TEMPLATE names a template ("projects/<p>/locations/<l>/templates/<t>"),
so local runs, tests and a deploy without the template behave exactly as before.

Fails open. A Model Armor timeout or error returns `source="error"` and the turn goes ahead: the
customer agent's own guardrails (consent, STOP, cite-or-drop, code-priced orders) still hold, and a
screening outage must not take the demo chat down with it. Every verdict carries its `source` so a
fail-open turn is visible in the response, never silent.
"""

from __future__ import annotations

import os
import re
import threading
from dataclasses import dataclass
from typing import Any

import httpx

TEMPLATE_ENV = "TAAL_MODEL_ARMOR_TEMPLATE"
TIMEOUT_S = float(os.environ.get("TAAL_MODEL_ARMOR_TIMEOUT_S", "1.5"))
_TEMPLATE_RE = re.compile(r"^projects/[^/]+/locations/([a-z0-9-]+)/templates/[^/]+$")

BLOCKED_PROMPT_REPLY = "Sorry, I can't help with that message. I can help with offers, your orders, or stopping messages (reply STOP)."
BLOCKED_REPLY_TEXT = "Sorry, I couldn't send that reply. Please ask again, or reply STOP to stop messages."


@dataclass(frozen=True)
class Verdict:
    blocked: bool
    source: str  # "off" (no template), "model_armor" (screened), "error" (failed open)
    filters: tuple[str, ...] = ()
    detail: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {"blocked": self.blocked, "source": self.source, "filters": list(self.filters), **({"detail": self.detail} if self.detail else {})}


OFF = Verdict(blocked=False, source="off")

_creds_lock = threading.Lock()
_creds: Any = None


def template() -> str | None:
    t = (os.environ.get(TEMPLATE_ENV) or "").strip()
    return t if _TEMPLATE_RE.match(t) else None


def _token() -> str:
    global _creds
    import google.auth
    import google.auth.transport.requests

    with _creds_lock:
        if _creds is None:
            _creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        if not _creds.valid:
            _creds.refresh(google.auth.transport.requests.Request())
        return _creds.token


def _matched_filters(result: dict[str, Any]) -> tuple[str, ...]:
    """Names of the filters that reported MATCH_FOUND, e.g. ("pi_and_jailbreak", "rai")."""
    found = []
    for name, wrapper in (result.get("filterResults") or {}).items():
        for inner in (wrapper or {}).values():
            if isinstance(inner, dict) and inner.get("matchState") == "MATCH_FOUND":
                found.append(name)
                break
    return tuple(sorted(found))


def _call(method: str, payload: dict[str, Any], tmpl: str, client: httpx.Client | None = None) -> Verdict:
    location = _TEMPLATE_RE.match(tmpl).group(1)  # type: ignore[union-attr]
    url = f"https://modelarmor.{location}.rep.googleapis.com/v1/{tmpl}:{method}"
    try:
        http = client or httpx.Client(timeout=TIMEOUT_S)
        try:
            r = http.post(url, json=payload, headers={"Authorization": f"Bearer {_token()}"})
        finally:
            if client is None:
                http.close()
        r.raise_for_status()
        result = r.json().get("sanitizationResult") or {}
    except Exception as e:  # fail open: see module docstring
        return Verdict(blocked=False, source="error", detail=f"{type(e).__name__}: {str(e)[:200]}")
    blocked = result.get("filterMatchState") == "MATCH_FOUND"
    return Verdict(blocked=blocked, source="model_armor", filters=_matched_filters(result) if blocked else ())


def screen_prompt(text: str, client: httpx.Client | None = None) -> Verdict:
    tmpl = template()
    if not tmpl:
        return OFF
    return _call("sanitizeUserPrompt", {"userPromptData": {"text": text}}, tmpl, client)


def screen_reply(text: str, client: httpx.Client | None = None) -> Verdict:
    tmpl = template()
    if not tmpl:
        return OFF
    return _call("sanitizeModelResponse", {"modelResponseData": {"text": text}}, tmpl, client)
