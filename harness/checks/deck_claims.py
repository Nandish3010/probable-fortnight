"""Deck claims check: every path in deck/claims.md exists, and a cited line number is inside the file.

Run as `python3 harness/checks/deck_claims.py` (no third-party imports). It does not render the deck.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CLAIMS = ROOT / "deck" / "claims.md"
CITE = re.compile(r"`([^`]+)`")


def check() -> list[str]:
    problems: list[str] = []
    slides_seen: set[int] = set()
    for n, line in enumerate(CLAIMS.read_text(encoding="utf-8").splitlines(), 1):
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) != 3 or not cells[0].isdigit():
            continue
        slides_seen.add(int(cells[0]))
        cites = CITE.findall(cells[2])
        if not cites:
            problems.append(f"claims.md:{n}: no cited path")
        for cite in cites:
            path, _, lines = cite.partition(":")
            f = ROOT / path
            if not f.exists():
                problems.append(f"claims.md:{n}: {path} does not exist")
            elif lines and f.is_file():
                last = max(int(x) for x in re.findall(r"\d+", lines))
                if last > len(f.read_text(encoding="utf-8", errors="replace").splitlines()):
                    problems.append(f"claims.md:{n}: {cite} is past the end of the file")
    missing = set(range(1, 15)) - slides_seen
    if missing:
        problems.append(f"claims.md has no rows for slide(s) {sorted(missing)}")
    return problems


if __name__ == "__main__":
    found = check()
    for p in found:
        print("deck_claims:", p)
    print("deck_claims: ok" if not found else f"deck_claims: {len(found)} problem(s)")
    sys.exit(1 if found else 0)
