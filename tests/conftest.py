"""Shared fixtures. The generated tenant under TAAL_DATA_DIR (default .local/data) is reused when
present (make generate runs first in `make verify`); otherwise it is built once into a temp dir."""
from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from agents.gate.store import LocalStore, OverlayStore

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def data_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    d = Path(os.environ.get("TAAL_DATA_DIR", ".local/data"))
    if (d / "manifest.json").exists() and (d / "gaps.jsonl").exists():
        return d.resolve()
    out = tmp_path_factory.mktemp("tenant")
    import asyncio

    from data.generator import generate
    from harness.seed_plays import seed_plays
    from jobs.sense.run import run_sense

    generate(out)
    run_sense(out)
    asyncio.run(seed_plays(str(out)))
    return out


@pytest.fixture(scope="session")
def base_store(data_dir: Path) -> LocalStore:
    return LocalStore(data_dir)


@pytest.fixture
def sandbox(data_dir: Path, tmp_path: Path) -> OverlayStore:
    """A fresh copy-on-write sandbox over the base tenant for tests that mutate."""
    s = OverlayStore(data_dir, tmp_path / "overlay")
    yield s
    shutil.rmtree(tmp_path / "overlay", ignore_errors=True)
