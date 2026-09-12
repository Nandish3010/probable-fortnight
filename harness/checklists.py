"""Load component checklists (harness/checklists/*.md) and the ownership map (harness/ownership.toml)."""
from __future__ import annotations

import fnmatch
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECKLIST_DIR = ROOT / "harness" / "checklists"
OWNERSHIP = ROOT / "harness" / "ownership.toml"
DECISIONS = ROOT / "docs" / "DECISIONS.md"

_CHECKBOX = re.compile(r"^\s*- \[( |x|X)\] (.+)$")


@dataclass
class Checklist:
    component: str
    title: str
    owner: str
    spec_sections: list[str]
    tests: list[str]
    body: str
    items: list[tuple[bool, str]] = field(default_factory=list)
    path: Path | None = None

    @property
    def done(self) -> int:
        return sum(1 for checked, _ in self.items if checked)

    @property
    def total(self) -> int:
        return len(self.items)


def _parse_front_matter(text: str) -> tuple[dict[str, object], str]:
    """Minimal YAML front matter parser: scalars and flow lists of strings only."""
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end < 0:
        return {}, text
    head, body = text[3:end].strip("\n"), text[end + 4 :]
    meta: dict[str, object] = {}
    for line in head.splitlines():
        if ":" not in line:
            continue
        key, _, raw = line.partition(":")
        raw = raw.strip()
        if raw.startswith("[") and raw.endswith("]"):
            meta[key.strip()] = [
                v.strip().strip('"').strip("'") for v in raw[1:-1].split(",") if v.strip()
            ]
        else:
            meta[key.strip()] = raw.strip('"').strip("'")
    return meta, body


def load_checklist(path: Path) -> Checklist:
    text = path.read_text(encoding="utf-8")
    meta, body = _parse_front_matter(text)
    items = [(m.group(1).lower() == "x", m.group(2).strip()) for m in map(_CHECKBOX.match, body.splitlines()) if m]
    return Checklist(
        component=str(meta.get("component", path.stem)),
        title=str(meta.get("title", path.stem)),
        owner=str(meta.get("owner", "?")),
        spec_sections=list(meta.get("spec_sections", [])),  # type: ignore[arg-type]
        tests=list(meta.get("tests", [])),  # type: ignore[arg-type]
        body=body,
        items=items,
        path=path,
    )


def load_all() -> dict[str, Checklist]:
    """Checklists in ownership.toml order (the §17.3 row order), then any extras alphabetically."""
    order = list(load_ownership().keys())
    found = {c.component: c for c in (load_checklist(p) for p in sorted(CHECKLIST_DIR.glob("*.md")))}
    ordered = {k: found[k] for k in order if k in found}
    ordered.update({k: v for k, v in sorted(found.items()) if k not in ordered})
    return ordered


def load_ownership() -> dict[str, list[str]]:
    with open(OWNERSHIP, "rb") as f:
        data = tomllib.load(f)
    return {k: list(v.get("paths", [])) for k, v in data.items()}


def _glob_match(path: str, pattern: str) -> bool:
    if pattern.endswith("/**"):
        prefix = pattern[:-3]
        return path == prefix or path.startswith(prefix + "/")
    return fnmatch.fnmatch(path, pattern)


def components_for_paths(paths: list[str]) -> list[str]:
    owned = load_ownership()
    hit = [c for c, globs in owned.items() if any(_glob_match(p, g) for p in paths for g in globs)]
    return hit


def spec_section(number: str, text: str | None = None) -> str:
    """Extract a numbered section (e.g. "5.3" or "11a") from docs/DECISIONS.md, up to the next heading of
    the same or a higher level. Returns an empty string when the section is not found."""
    text = text if text is not None else DECISIONS.read_text(encoding="utf-8")
    lines = text.splitlines()
    head = re.compile(rf"^(#+)\s+{re.escape(number)}(\.|\s)")
    start = level = None
    for i, line in enumerate(lines):
        m = head.match(line)
        if m:
            start, level = i, len(m.group(1))
            break
    if start is None:
        return ""
    out = [lines[start]]
    for line in lines[start + 1 :]:
        m = re.match(r"^(#+)\s", line)
        if m and len(m.group(1)) <= level:
            break
        out.append(line)
    return "\n".join(out).strip()
