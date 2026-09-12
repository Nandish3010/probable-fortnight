"""Local file store standing in for BigQuery (system of record) and Firestore (serving).

Layout: TAAL_DATA_DIR/<table>.jsonl, one JSON object per line, named after the BigQuery DDL
tables in data/bigquery/ddl. Agent traces go to TAAL_DATA_DIR/events/<run_id>.jsonl.
In production these calls are replaced by BigQuery/Firestore clients behind the same interface.
"""
from __future__ import annotations

import json
import os
from collections.abc import Iterable
from pathlib import Path
from typing import Any


class LocalStore:
    def __init__(self, root: str | Path | None = None):
        self.root = Path(root or os.environ.get("TAAL_DATA_DIR", ".local/data"))
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "events").mkdir(exist_ok=True)

    def _path(self, table: str) -> Path:
        return self.root / f"{table}.jsonl"

    def read(self, table: str) -> list[dict[str, Any]]:
        p = self._path(table)
        if not p.exists():
            return []
        with open(p, encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]

    def write(self, table: str, rows: Iterable[dict[str, Any]]) -> None:
        with open(self._path(table), "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")

    def append(self, table: str, rows: Iterable[dict[str, Any]]) -> None:
        with open(self._path(table), "a", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")

    def upsert(self, table: str, key: str, row: dict[str, Any]) -> None:
        rows = [r for r in self.read(table) if r.get(key) != row.get(key)]
        rows.append(row)
        self.write(table, rows)

    def find(self, table: str, **eq: Any) -> list[dict[str, Any]]:
        return [r for r in self.read(table) if all(r.get(k) == v for k, v in eq.items())]

    def append_event(self, run_id: str, event: dict[str, Any]) -> None:
        with open(self.root / "events" / f"{run_id}.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")

    def read_events(self, run_id: str) -> list[dict[str, Any]]:
        p = self.root / "events" / f"{run_id}.jsonl"
        if not p.exists():
            return []
        with open(p, encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]


class OverlayStore(LocalStore):
    """Copy-on-write view over a base store for per-visitor judge-mode sandboxes (DECISIONS §5.6).

    Reads come from the overlay when the table has been touched there, else from the base.
    Every write lands in the overlay (the base table is copied on first write so appends and
    upserts see the full table). Events always live in the overlay. `reset()` deletes the overlay.
    """

    def __init__(self, base_root: str | Path, overlay_root: str | Path):
        self.base = LocalStore(base_root)
        super().__init__(overlay_root)

    def _path(self, table: str) -> Path:
        p = self.root / f"{table}.jsonl"
        if p.exists():
            return p
        return self.base._path(table)

    def _materialise(self, table: str) -> Path:
        p = self.root / f"{table}.jsonl"
        if not p.exists():
            src = self.base._path(table)
            if src.exists():
                p.write_bytes(src.read_bytes())
            else:
                p.touch()
        return p

    def write(self, table: str, rows: Iterable[dict[str, Any]]) -> None:
        self._materialise(table)
        with open(self.root / f"{table}.jsonl", "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")

    def append(self, table: str, rows: Iterable[dict[str, Any]]) -> None:
        p = self._materialise(table)
        with open(p, "a", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")

    def reset(self) -> None:
        import shutil

        shutil.rmtree(self.root, ignore_errors=True)
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "events").mkdir(exist_ok=True)

    def touched_tables(self) -> list[str]:
        return sorted(p.stem for p in self.root.glob("*.jsonl"))
