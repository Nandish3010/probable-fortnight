"""data.ingest: the three-CSV contract, the sell-by derivation under the tenant's rule, the committed
samples, and the round-trip (seeded tenant -> CSVs -> ingest -> identical Sense gaps)."""
from __future__ import annotations

import json
import shutil
from datetime import date
from pathlib import Path

import pytest

from agents.gate.store import LocalStore
from data.generator import generate
from data.ingest.__main__ import main as ingest_main
from data.ingest.export import export

ROOT = Path(__file__).resolve().parents[2]
SAMPLES = ROOT / "data" / "samples"
TENANT = str(ROOT / "config" / "tenant.demo.toml")


@pytest.fixture(scope="module")
def seeded(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("seeded")
    generate(out, 20260912)
    return out


def _run(tmp_path: Path, *extra: str, products: Path | None = None, batches: Path | None = None, sales: Path | None = None, tenant: str = TENANT) -> tuple[int, Path]:
    out = tmp_path / "out"
    argv = ["--products", str(products or SAMPLES / "products.csv"), "--batches", str(batches or SAMPLES / "inventory_batches.csv"),
            "--sales", str(sales or SAMPLES / "sales.csv"), "--tenant", tenant, "--out", str(out), *extra]
    return ingest_main(argv), out


def test_committed_samples_are_the_seeded_generator_export(seeded: Path, tmp_path: Path) -> None:
    """Guards the secrets.py exemption for data/samples/*.csv: the files must be exactly what the
    seeded synthetic generator exports, so no real partner file can be committed in their place."""
    export(seeded, tmp_path, sample=True)
    committed = sorted(p.name for p in SAMPLES.glob("*.csv"))
    assert committed == sorted(p.name for p in tmp_path.glob("*.csv"))
    for name in committed:
        assert (SAMPLES / name).read_bytes() == (tmp_path / name).read_bytes(), name
        assert len((SAMPLES / name).read_text(encoding="utf-8").splitlines()) <= 201


def test_samples_flag_the_planted_chips_lot_under_the_sellby_rule(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, out = _run(tmp_path)
    assert code == 0
    batches = {b["batch_id"]: b for b in LocalStore(out).read("inventory_batches")}
    # 90-day shelf life, expiry 2026-10-15, "either" rule -> cut-off min(27, 45) = 27 days earlier.
    assert batches["B-CHIPS-DS07-01"]["online_sellby_date"] == "2026-09-18"
    assert batches["B-CHIPS-DS07-01"]["sellby_rule_version"] == "v1-either"
    chips = next(g for g in LocalStore(out).read("gaps") if g["batch_id"] == "B-CHIPS-DS07-01")
    assert (chips["type"], chips["units_at_risk"], chips["rupees_at_stake"]) == ("online_sellby_breach", 368, 9200.0)
    report = json.loads((out / "ingest_report.json").read_text(encoding="utf-8"))
    assert report["as_of"] == "2026-09-12"  # day after the last sales date
    assert report["sellby_flagged"]["lots"] == 2
    assert report["top_gaps"][0]["rupees_at_stake"] >= report["top_gaps"][-1]["rupees_at_stake"]
    text = capsys.readouterr().out
    assert "Lots flagged under the online sell-by rule: 2 lots" in text
    assert "no nodes.csv" in text  # the default it applied is said out loud


def test_the_tenant_rule_not_a_constant_sets_the_sellby_date(tmp_path: Path) -> None:
    strict = tmp_path / "tenant.strict.toml"
    strict.write_text(Path(TENANT).read_text(encoding="utf-8").replace('combine = "min"', 'combine = "max"').replace('version = "v1-either"', 'version = "v1-strict"'), encoding="utf-8")
    code, out = _run(tmp_path, tenant=str(strict))
    assert code == 0
    b = next(b for b in LocalStore(out).read("inventory_batches") if b["batch_id"] == "B-CHIPS-DS07-01")
    # max(27, 45) = 45 days before 2026-10-15: already past on the as-of date.
    assert (b["online_sellby_date"], b["sellby_rule_version"]) == ("2026-08-31", "v1-strict")
    # Sense raises no gap for it (expiry is past the 28-day horizon), so the report counts it
    # directly: 440 units that can no longer be sold online. A known limit of Sense, stated here.
    assert not [g for g in LocalStore(out).read("gaps") if g["batch_id"] == "B-CHIPS-DS07-01"]
    report = json.loads((out / "ingest_report.json").read_text(encoding="utf-8"))
    assert report["sellby_rule"] == "v1-strict"
    assert report["past_online_sellby_on_hand"]["units"] >= 440


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_contract_violations_are_all_reported_and_nothing_is_written(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    products = _write(tmp_path / "p.csv", (SAMPLES / "products.csv").read_text(encoding="utf-8").replace(",true\n", ",maybe\n", 1))
    batches = _write(tmp_path / "b.csv", "batch_id,sku,node_id,qty_on_hand,expiry_date,received_at,source\nB1,SKU-MASALA-CHIPS-200G,DS-07,-4,15/10/2026,,system\n")
    sales = _write(tmp_path / "s.csv", "date,sku,node_id,units,revenue,on_promo\n2026-09-01,SKU-MASALA-CHIPS-200G,DS-07,3,,false\n")
    code, out = _run(tmp_path, products=products, batches=batches, sales=sales)
    err = capsys.readouterr().err
    assert code == 2
    assert not out.exists()
    assert "column 'is_food' value 'maybe'" in err
    assert "b.csv:2: column 'qty_on_hand' value '-4': must be >= 0" in err
    assert "b.csv:2: column 'expiry_date' value '15/10/2026'" in err
    assert "s.csv" not in err  # a blank revenue cell is allowed; the sales file is valid
    assert "nothing was written" in err


def test_sales_header_must_carry_every_required_column(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    sales = _write(tmp_path / "s.csv", "date,sku,units,on_promo\n2026-09-01,SKU-MASALA-CHIPS-200G,3,false\n")
    code, _ = _run(tmp_path, sales=sales)
    assert code == 2
    assert "missing required column(s) node_id, revenue" in capsys.readouterr().err


def test_cross_file_references_and_duplicates_are_checked(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    rows = (SAMPLES / "inventory_batches.csv").read_text(encoding="utf-8").splitlines()
    batches = _write(tmp_path / "b.csv", "\n".join([*rows, rows[1], rows[1].replace("SKU-MASALA-CHIPS-200G", "SKU-NOT-SOLD").replace("B-CHIPS", "B-OTHER")]) + "\n")
    code, _ = _run(tmp_path, batches=batches)
    err = capsys.readouterr().err
    assert code == 2
    assert "duplicate batch_id 'B-CHIPS-DS07-01'" in err
    assert "1 sku(s) not in products.csv, e.g. SKU-NOT-SOLD" in err


def test_refuses_to_overwrite_an_existing_store(tmp_path: Path) -> None:
    assert _run(tmp_path)[0] == 0
    assert _run(tmp_path)[0] == 3


def test_nothing_leaves_the_machine_even_if_the_env_asks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("TAAL_BATCH_STORE", "bigquery")
    monkeypatch.setenv("TAAL_FORECAST_BACKEND", "bigquery_timesfm")
    monkeypatch.setenv("TAAL_SERVING_CACHE", "firestore")
    code, out = _run(tmp_path)
    assert code == 0
    assert (out / "gaps.jsonl").exists()
    text = capsys.readouterr().out
    assert "TAAL_BATCH_STORE=bigquery ignored" in text and "TAAL_SERVING_CACHE=firestore ignored" in text


def test_roundtrip_seeded_tenant_gives_identical_gaps(tmp_path: Path) -> None:
    from harness.ingest_roundtrip import roundtrip

    summary, gaps_diff, _ = roundtrip(tmp_path)
    assert gaps_diff == ""
    assert summary["pass"] is True
    assert summary["gaps"]["ingested"] == summary["gaps"]["seeded_grocery"] > 0
    assert summary["forecasts"]["identical"] is True
    assert summary["online_sellby_date"]["mismatches"] == 0
    assert summary["ingest_report"]["as_of"] == date(2026, 9, 12).isoformat()
    shutil.rmtree(tmp_path, ignore_errors=True)
