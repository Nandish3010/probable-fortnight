"""Docs lint: README shape, relative links, vendor names in markdown, DECISIONS present.

Run as `python3 harness/checks/docs_lint.py` (no third-party imports). Fails when:
- README.md does not start with the title line, or has no "Judge quick-start" section in the first 40 lines;
- any relative markdown link in README.md or docs/**/*.md points at a missing file;
- any tracked or untracked markdown file mentions an assistant/AI-vendor name (pattern shared with secrets.py);
- docs/DECISIONS.md is missing.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from harness.checks.secrets import PATTERNS  # noqa: E402

TITLE = "# Taal"
QUICK_START = re.compile(r"^##+\s+Judge quick-start", re.I)
LINK = re.compile(r"(?<!\!)\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
IMAGE = re.compile(r"\!\[[^\]]*\]\(([^)\s]+)\)")
VENDOR = PATTERNS["assistant/model vendor name"]


def markdown_files() -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "--", "*.md", "**/*.md"],
        capture_output=True, text=True, cwd=ROOT,
    ).stdout.split("\n")
    return [ROOT / p for p in out if p and (ROOT / p).is_file()]


def check_readme(problems: list[str]) -> None:
    readme = ROOT / "README.md"
    if not readme.exists():
        problems.append("README.md missing")
        return
    lines = readme.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != TITLE:
        problems.append(f"README.md must start with '{TITLE}' (got {lines[0]!r} on line 1)" if lines else "README.md is empty")
    if not any(QUICK_START.match(line) for line in lines[:40]):
        problems.append("README.md has no 'Judge quick-start' section within the first 40 lines")


def check_links(problems: list[str]) -> None:
    files = [ROOT / "README.md", *sorted((ROOT / "docs").rglob("*.md"))]
    for f in files:
        if not f.exists():
            continue
        text = f.read_text(encoding="utf-8")
        for m in list(LINK.finditer(text)) + list(IMAGE.finditer(text)):
            target = m.group(1)
            if re.match(r"^[a-z][a-z0-9+.-]*:", target) or target.startswith("#"):
                continue  # absolute URL, mailto, or in-page anchor
            rel = target.split("#", 1)[0]
            if not rel:
                continue
            if not (f.parent / rel).exists():
                problems.append(f"broken link in {f.relative_to(ROOT)}: {target}")


def check_vendor_names(problems: list[str]) -> None:
    for f in markdown_files():
        text = f.read_text(encoding="utf-8", errors="ignore")
        m = VENDOR.search(text)
        if m:
            line = text.count("\n", 0, m.start()) + 1
            problems.append(f"assistant/AI-vendor name in {f.relative_to(ROOT)}:{line}")


def main() -> int:
    problems: list[str] = []
    if not (ROOT / "docs" / "DECISIONS.md").exists():
        problems.append("docs/DECISIONS.md missing")
    check_readme(problems)
    check_links(problems)
    check_vendor_names(problems)
    for p in problems:
        print(p)
    print("docs: clean" if not problems else f"docs: {len(problems)} finding(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
