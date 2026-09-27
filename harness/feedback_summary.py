"""Summarise real practitioner feedback into eval/raw/feedback_summary_<date>/summary.{json,md}.

    uv run python -m harness.feedback_summary                      # reads TAAL_FEEDBACK_STORE
    TAAL_FEEDBACK_STORE=firestore GOOGLE_CLOUD_PROJECT=... uv run python -m harness.feedback_summary
    uv run python -m harness.feedback_summary --export responses.json   # an owner-provided export instead

The deck's feedback numbers come from these two files and nothing else. Only `source: "real"`
rows are counted (services/feedback/summary.py::summarize); contact details are never read.
config/feedback_exclusions.json lists the rows the owner has excluded, the minimum number of
substantive answers, whether to force counts, and whose quotes are cleared. Excluded ids are
printed for the owner and never written to the summary.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from services.feedback.intake import form
from services.feedback.store import build_store, feedback_backend
from services.feedback.summary import (
    EXCLUSIONS_PATH,
    exclusion_config,
    exclusions,
    render_markdown,
    summarize,
)

ROOT = Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out-dir", default=str(ROOT / "eval" / "raw"))
    ap.add_argument("--export", default=None, help="JSON list or JSONL of response records exported by the owner (answers only)")
    ap.add_argument("--exclusions", default=str(EXCLUSIONS_PATH))
    args = ap.parse_args(argv)
    now = datetime.now(UTC)
    generated_at = now.isoformat(timespec="seconds").replace("+00:00", "Z")
    records = load_export(Path(args.export)) if args.export else build_store().responses()
    kw = exclusion_config(Path(args.exclusions))
    summary = summarize(records, form(), generated_at, **kw)
    summary["store"] = "export" if args.export else feedback_backend()
    out = Path(args.out_dir) / f"feedback_summary_{now.date().isoformat()}"
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out / "summary.md").write_text(render_markdown(summary), encoding="utf-8")
    n = summary["responses"]
    print(f"feedback summary: {n['total']} real response(s) (self {n['self']}, interview {n['interview']}), "
          f"{summary['excluded_non_real']} excluded {summary['excluded_by_reason']}, store={summary['store']} -> {out}/summary.json / .md")
    dropped = exclusions(records, form(), kw["exclude_ids"], kw["min_substantive"])
    print(f"for the owner, not committed: below {kw['min_substantive']} substantive answers: {dropped['below_min_substantive']}; flagged: {dropped['flagged']}")
    return 0


def load_export(path: Path) -> list[dict]:
    """Response records only; a contact field in an export is dropped before anything reads it."""
    text = path.read_text(encoding="utf-8")
    rows = json.loads(text) if text.lstrip().startswith("[") else [json.loads(line) for line in text.splitlines() if line.strip()]
    keep = ("response_id", "submitted_at", "form_version", "mode", "source", "answers")
    out = []
    for r in rows:
        rec = {k: r[k] for k in keep if k in r}
        rec["answers"] = {k: v for k, v in (rec.get("answers") or {}).items() if k != "e3_contact"}
        out.append(rec)
    return out


if __name__ == "__main__":
    sys.exit(main())
