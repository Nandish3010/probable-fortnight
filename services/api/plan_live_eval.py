"""The committed live-plan evidence summary that /health reports as `plan_live_eval`.

Read once at startup from eval/raw/plan_live_2026-10-12.json (the file ships in the image). Fail
soft: a missing, unreadable or malformed file yields None and /health simply omits the field --
a health endpoint must never fail because an evidence file is absent.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

SOURCE = "eval/raw/plan_live_2026-10-12.json"
_ROOT = Path(__file__).resolve().parents[2]

log = logging.getLogger(__name__)


def load_plan_live_eval(root: Path | None = None, source: str = SOURCE) -> dict[str, Any] | None:
    try:
        raw = json.loads(((root or _ROOT) / source).read_text())
        s = raw["summary"]
        return {
            "date": str(raw["date"]),
            "passed": int(s["passed"]),
            "total": int(s["total"]),
            "p50_s": float(s["p50_s"]),
            "source": source,
        }
    except (OSError, ValueError, KeyError, TypeError) as e:
        log.info("plan_live_eval omitted from /health: %s", e)
        return None
