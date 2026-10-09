"""Round-trip proof for the three-CSV contract: seeded tenant -> CSVs -> data.ingest -> Sense, and
the gaps must come out identical to Sense on the seeded tenant itself.

    uv run python -m harness.ingest_roundtrip [--out eval/raw/ingest_roundtrip_<date>]

Steps (all in a temp dir; nothing touches TAAL_DATA_DIR):
  1. data.generator --seed 20260912 -> A; jobs.sense on A            (the reference)
  2. data.ingest.export A -> CSVs (products, inventory_batches, sales, nodes, inbound)
  3. python -m data.ingest on those CSVs -> B                          (runs Sense on B)
  4. diff: every grocery gap row (canonical JSON, evidence included), every forecast row, and every
     batch's derived online_sellby_date. Gap types outside the grocery contract are reported separately.
Exit 0 only when all three diffs are empty.
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path
from typing import Any

from agents.gate.store import LocalStore
from data.generator import generate
from data.ingest.export import export
from data.ingest.ingest import GROCERY_GAP_TYPES
from jobs.sense.run import run_sense

ROOT = Path(__file__).resolve().parents[1]
SEED = 20260912
TENANT = "config/tenant.demo.toml"


def _canon(rows: list[dict[str, Any]]) -> list[str]:
    return sorted(json.dumps(r, sort_keys=True, ensure_ascii=False) for r in rows)


def _digest(lines: list[str]) -> str:
    return hashlib.sha256("\n".join(lines).encode()).hexdigest()


def roundtrip(work: Path) -> tuple[dict[str, Any], str, str]:
    a, csvs, b = work / "seeded", work / "csv", work / "ingested"
    generate(a, SEED)
    run_sense(a)
    counts = export(a, csvs)
    cmd = [sys.executable, "-m", "data.ingest", "--products", str(csvs / "products.csv"), "--batches", str(csvs / "inventory_batches.csv"),
           "--sales", str(csvs / "sales.csv"), "--nodes", str(csvs / "nodes.csv"), "--inbound", str(csvs / "inbound.csv"),
           "--tenant", TENANT, "--out", str(b)]
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT)
    if proc.returncode != 0:
        raise SystemExit(f"data.ingest failed ({proc.returncode}):\n{proc.stderr}")
    sa, sb = LocalStore(a), LocalStore(b)
    gaps_a_all = sa.read("gaps")
    gaps_a = [g for g in gaps_a_all if g["type"] in GROCERY_GAP_TYPES]
    gaps_b = sb.read("gaps")
    ca, cb = _canon(gaps_a), _canon(gaps_b)
    gaps_diff = "".join(difflib.unified_diff([x + "\n" for x in ca], [x + "\n" for x in cb], "seeded/gaps.jsonl (grocery types)", "ingested/gaps.jsonl"))
    fa, fb = _canon(sa.read("forecasts")), _canon(sb.read("forecasts"))
    sellby_a = {r["batch_id"]: r["online_sellby_date"] for r in sa.read("inventory_batches")}
    sellby_b = {r["batch_id"]: r["online_sellby_date"] for r in sb.read("inventory_batches")}
    sellby_mismatch = sorted(k for k in sellby_a.keys() | sellby_b.keys() if sellby_a.get(k) != sellby_b.get(k))
    report = json.loads((b / "ingest_report.json").read_text(encoding="utf-8"))
    summary = {
        "command": "uv run python -m harness.ingest_roundtrip",
        "label": "measured on the seeded synthetic tenant (data/generator seed 20260912), not partner data",
        "seed": SEED, "tenant_config": TENANT, "as_of": report["as_of"],
        "exported_csv_rows": counts,
        "gaps": {
            "seeded_total": len(gaps_a_all), "seeded_grocery": len(gaps_a), "ingested": len(gaps_b),
            "excluded_out_of_contract": {t: sum(1 for g in gaps_a_all if g["type"] == t) for t in sorted({g["type"] for g in gaps_a_all} - set(GROCERY_GAP_TYPES))},
            "sha256_seeded_grocery": _digest(ca), "sha256_ingested": _digest(cb), "diff_lines": len(gaps_diff.splitlines()),
        },
        "forecasts": {"seeded": len(fa), "ingested": len(fb), "identical": fa == fb, "sha256_seeded": _digest(fa), "sha256_ingested": _digest(fb)},
        "online_sellby_date": {"batches": len(sellby_a), "mismatches": len(sellby_mismatch), "examples": sellby_mismatch[:5]},
        "ingest_report": report,
    }
    summary["pass"] = not gaps_diff and summary["forecasts"]["identical"] and not sellby_mismatch
    return summary, gaps_diff, proc.stdout.replace(str(work), "<tmp>")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=f"eval/raw/ingest_roundtrip_{date.today().isoformat()}")
    args = ap.parse_args(argv)
    with tempfile.TemporaryDirectory() as tmp:
        summary, gaps_diff, stdout = roundtrip(Path(tmp))
    out = ROOT / args.out
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (out / "gaps.diff").write_text(gaps_diff, encoding="utf-8")
    (out / "ingest_stdout.txt").write_text(stdout, encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ("pass", "gaps", "forecasts", "online_sellby_date")}, indent=2))
    print(f"wrote {out.relative_to(ROOT)}/summary.json, gaps.diff ({summary['gaps']['diff_lines']} lines), ingest_stdout.txt")
    return 0 if summary["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
