"""harness.prior_update_demo against the generated tenant: reproduces the committed file byte for
byte and leaves the base tenant (flagship play, estimator_priors) exactly as it was."""
import hashlib
import json
from pathlib import Path

from harness.prior_update_demo import FLAGSHIP_PLAY_ID, build, check

RAW = Path(__file__).resolve().parents[2] / "eval" / "raw" / "prior_update_2026-09-27.json"


def _digest(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def test_build_matches_the_committed_evidence_and_does_not_touch_the_base_tenant(data_dir):
    before = {t: _digest(data_dir / f"{t}.jsonl") for t in ("plays", "estimator_priors", "order_lines", "play_assignments", "play_outcomes") if (data_dir / f"{t}.jsonl").exists()}
    result = build(data_dir)
    check(result)
    assert json.dumps(result, indent=2, ensure_ascii=False) + "\n" == RAW.read_text(encoding="utf-8")
    assert before == {t: _digest(data_dir / f"{t}.jsonl") for t in before}
    play = next(json.loads(r["play_json"]) for r in map(json.loads, (data_dir / "plays.jsonl").read_text().splitlines()) if r["play_id"] == FLAGSHIP_PLAY_ID)
    assert play["status"] == "proposed"
