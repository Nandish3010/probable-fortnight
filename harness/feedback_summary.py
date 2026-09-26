"""Summarise real practitioner feedback into eval/raw/feedback_summary_<date>.{json,md}.

    uv run python -m harness.feedback_summary                      # reads TAAL_FEEDBACK_STORE
    TAAL_FEEDBACK_STORE=firestore GOOGLE_CLOUD_PROJECT=... uv run python -m harness.feedback_summary

The deck's feedback numbers come from these two files and nothing else. Only `source: "real"`
rows are counted (services/feedback/summary.py::summarize); contact details are never read.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from services.feedback.intake import form
from services.feedback.store import build_store, feedback_backend
from services.feedback.summary import render_markdown, summarize

ROOT = Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out-dir", default=str(ROOT / "eval" / "raw"))
    args = ap.parse_args(argv)
    now = datetime.now(UTC)
    generated_at = now.isoformat(timespec="seconds").replace("+00:00", "Z")
    summary = summarize(build_store().responses(), form(), generated_at)
    summary["store"] = feedback_backend()
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    stem = out / f"feedback_summary_{now.date().isoformat()}"
    stem.with_suffix(".json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    stem.with_suffix(".md").write_text(render_markdown(summary), encoding="utf-8")
    n = summary["responses"]
    print(f"feedback summary: {n['total']} real response(s) (self {n['self']}, interview {n['interview']}), "
          f"{summary['excluded_non_real']} excluded, store={summary['store']} -> {stem}.json / .md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
