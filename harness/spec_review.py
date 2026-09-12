"""Reviewer-agent verdict on a diff.

Usage: python -m harness.spec_review --base origin/main --out eval/spec_review.md

Computes `git diff <base>...HEAD`, picks the checklists whose owned paths changed
(harness/ownership.toml), builds the Reviewer prompt (harness/prompts/reviewer.md + spec sections +
checklists + diff) and, when TAAL_MODEL_BACKEND=vertex and GOOGLE_CLOUD_PROJECT is set, sends it to
Gemini on Vertex AI with the model id from config/models.toml. Otherwise it writes a
"skipped: no project" verdict. Exit code: 0 in skipped mode; 1 on FAIL (or an error) in vertex mode.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

from agents.gate.config import load_models
from harness.checklists import ROOT, components_for_paths, load_all, spec_section

REVIEWER_PROMPT = ROOT / "harness" / "prompts" / "reviewer.md"
MAX_DIFF_CHARS = 120_000
_VERDICT = re.compile(r"^\s*VERDICT:\s*(PASS|FAIL)\b", re.M)


def git(*args: str) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True, check=True, cwd=ROOT).stdout


def changed_files(base: str) -> list[str]:
    return [p for p in git("diff", "--name-only", f"{base}...HEAD").split("\n") if p]


def build_prompt(base: str, files: list[str], components: list[str]) -> str:
    checklists = load_all()
    diff = git("diff", f"{base}...HEAD")
    if len(diff) > MAX_DIFF_CHARS:
        diff = diff[:MAX_DIFF_CHARS] + "\n... [diff truncated by spec_review] ...\n"
    parts = [REVIEWER_PROMPT.read_text(encoding="utf-8"), "\n\n# Inputs\n"]
    parts.append(f"Base: `{base}`. Changed files:\n" + "\n".join(f"- {f}" for f in files) + "\n")
    sections: list[str] = []
    for c in components:
        cl = checklists.get(c)
        if cl is None:
            continue
        parts.append(f"\n## Checklist: {c}\n\n" + cl.path.read_text(encoding="utf-8") if cl.path else "")
        sections.extend(s for s in cl.spec_sections if s not in sections)
    for s in sections:
        text = spec_section(s)
        if text:
            parts.append(f"\n## Spec §{s}\n\n{text}\n")
    parts.append("\n## Diff\n\n```diff\n" + diff + "\n```\n")
    parts.append("\nWrite the verdict now in the required format.\n")
    return "".join(parts)


def call_vertex(prompt: str, project: str) -> str:
    from google import genai  # imported lazily: only needed in vertex mode

    models = load_models()
    location = os.environ.get("GOOGLE_CLOUD_LOCATION") or models["vertex"]["location"]
    client = genai.Client(vertexai=True, project=project, location=location)
    model_id = models["ids"]["flash"]
    response = client.models.generate_content(model=model_id, contents=prompt)
    return f"<!-- model: {model_id} · location: {location} -->\n{response.text or ''}"


def write_verdict(out: Path, title: str, body: str) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(f"# Spec review: {title}\n\n{body}\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", required=True, help="git ref to diff against (e.g. origin/main)")
    ap.add_argument("--out", required=True, help="markdown verdict file")
    ap.add_argument("--dry-run", action="store_true", help="print the prompt and exit 0")
    args = ap.parse_args(argv)
    out = Path(args.out)

    try:
        files = changed_files(args.base)
    except subprocess.CalledProcessError as e:
        write_verdict(out, "skipped", f"skipped: cannot diff against `{args.base}` ({e.stderr.strip()})")
        print(f"spec_review: skipped (bad base {args.base!r})")
        return 0
    components = components_for_paths(files)
    summary = (
        f"Changed files: {len(files)}. Components touched: "
        + (", ".join(components) if components else "none (no owned path changed)")
    )
    if not files or not components:
        write_verdict(out, "PASS (nothing to review)", f"VERDICT: PASS\n\n{summary}\n\nNo checklist applies to this diff.")
        print(f"spec_review: PASS, {summary}")
        return 0

    prompt = build_prompt(args.base, files, components)
    if args.dry_run:
        print(prompt)
        return 0

    backend = os.environ.get("TAAL_MODEL_BACKEND", "stub")
    models = load_models()
    project = os.environ.get(models["vertex"]["project_env"], "")
    if backend != "vertex" or not project:
        reason = "no project" if not project else f"backend={backend}"
        write_verdict(
            out,
            "skipped",
            f"skipped: {reason}\n\n{summary}\n\nSet TAAL_MODEL_BACKEND=vertex and GOOGLE_CLOUD_PROJECT to run the Reviewer.\n"
            f"Prompt size: {len(prompt)} chars.",
        )
        print(f"spec_review: skipped ({reason}); {summary}")
        return 0

    try:
        verdict_text = call_vertex(prompt, project)
    except Exception as e:  # noqa: BLE001 - any client error is a review failure in vertex mode
        write_verdict(out, "ERROR", f"VERDICT: FAIL\n\nReviewer call failed: {type(e).__name__}: {e}\n\n{summary}")
        print(f"spec_review: FAIL (reviewer call failed: {e})")
        return 1
    m = _VERDICT.search(verdict_text)
    verdict = m.group(1) if m else "FAIL"
    if not m:
        verdict_text = "VERDICT: FAIL (no verdict line in reviewer output; defaulting to FAIL)\n\n" + verdict_text
    write_verdict(out, verdict, f"{summary}\n\n{verdict_text}")
    print(f"spec_review: {verdict}; {summary}")
    return 1 if verdict == "FAIL" else 0


if __name__ == "__main__":
    sys.exit(main())
