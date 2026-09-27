"""Vision accuracy on real phone photos, through the exact function the API serves.

    TAAL_MODEL_BACKEND=vertex GOOGLE_APPLICATION_CREDENTIALS=... GOOGLE_CLOUD_PROJECT=amru-509214 \\
      uv run python -m harness.vision_real_eval --dir eval/raw/vision_real_2026-09-2X --passes 3

Input: `<dir>/photos/photo_NN.jpg` and `<dir>/labels.json`, both written by
`harness.vision_real_prep` (EXIF-stripped, downscaled). Each photo is sent as an uploaded data URL
to `agents.capture.vision.intake` -- the function `POST /capture` calls for an upload -- so the
prompt, schema, two-pass re-read and confidence flagging are the served ones, not a copy.

Scored per photo per pass (labels.csv has one product per photo; the model returns one row per
product block, so the row scored is the one whose SKU name matches the label, else the row with
the highest sku_confidence, and units are summed over every row carrying that SKU):

- product: normalised catalogue name of `sku_guess` == normalised `product_name` (exact), or one
  token set contains the other (tolerant). `in_catalogue` records whether the labelled product
  exists in the demo catalogue at all -- the prompt makes the model choose from that catalogue,
  so an out-of-catalogue product cannot score a product match by construction.
- best_before: exact date.
- units: `facings_count` total vs `units_visible`, exact and within +-1.
- mrp: exact rupees, only if the row carries `mrp_inr`; vision.py does not extract MRP today, so
  it is reported as not measurable rather than as 0%.

Also: wall time per `intake` call (includes the second Gemini call when any date confidence is
below the threshold), consistency across passes, and confidence calibration against the
`needs_confirmation` flag the phone view uses to force a confirmation.

Writes `<dir>/results.json` (every call's raw rows) and `<dir>/summary.md`. A run on any backend
other than `vertex` is labelled NOT A MEASUREMENT in both files.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agents.capture.vision import CONFIDENCE_THRESHOLD, intake
from agents.gate.config import load_models
from agents.gate.store import LocalStore

NODE_ID = "DS-07"


def norm_tokens(name: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", (name or "").lower())


def product_match(label: str, predicted: str) -> tuple[bool, bool]:
    """(exact, tolerant) normalised-name match."""
    a, b = norm_tokens(label), norm_tokens(predicted)
    if not a or not b:
        return False, False
    exact = a == b
    return exact, exact or set(a) <= set(b) or set(b) <= set(a)


def percentile(xs: list[float], p: float) -> float | None:
    """Nearest-rank percentile (no interpolation), so the value is always one observed call."""
    if not xs:
        return None
    s = sorted(xs)
    k = max(0, min(len(s) - 1, -(-len(s) * p // 100) - 1))
    return s[int(k)]


def score(label: dict[str, Any], rows: list[dict[str, Any]], names: dict[str, str]) -> dict[str, Any]:
    """One photo, one call: which row was scored, and each field's verdict."""
    in_catalogue = any(product_match(label["product_name"], n)[0] for n in names.values())
    if not rows:
        return {"scored_row": None, "in_catalogue": in_catalogue, "product_exact": False, "product_tolerant": False,
                "date_exact": False, "units_exact": False, "units_pm1": False, "mrp_exact": None,
                "min_confidence": None, "needs_confirmation": None, "wrong": True, "fields_wrong": 3}
    matching = [r for r in rows if product_match(label["product_name"], names.get(r["sku_guess"], r["sku_guess"]))[0]]
    row = matching[0] if matching else max(rows, key=lambda r: r["sku_confidence"])
    sku = row["sku_guess"]
    pexact, ptol = product_match(label["product_name"], names.get(sku, sku))
    units = sum(int(r["facings_count"]) for r in rows if r["sku_guess"] == sku)
    date_ok = row.get("best_before_date") == label["best_before_date"]
    mrp = None
    if "mrp_inr" in row and label.get("mrp_inr") is not None:
        mrp = row["mrp_inr"] is not None and abs(float(row["mrp_inr"]) - float(label["mrp_inr"])) < 0.5
    fields_wrong = (not pexact) + (not date_ok) + (units != label["units_visible"])
    return {
        "scored_row": row, "predicted_sku": sku, "predicted_name": names.get(sku, sku), "predicted_units": units,
        "in_catalogue": in_catalogue, "product_exact": pexact, "product_tolerant": ptol,
        "date_exact": date_ok, "units_exact": units == label["units_visible"],
        "units_pm1": abs(units - label["units_visible"]) <= 1, "mrp_exact": mrp,
        "min_confidence": min(row["sku_confidence"], row["date_confidence"], row["count_confidence"]),
        "date_confidence": row["date_confidence"],
        "needs_confirmation": bool(row.get("needs_confirmation")),
        "wrong": fields_wrong > 0, "fields_wrong": fields_wrong,
    }


def _rate(xs: list[bool]) -> dict[str, Any]:
    return {"n": len(xs), "correct": sum(xs), "rate": round(sum(xs) / len(xs), 4) if xs else None}


def aggregate(calls: list[dict[str, Any]], n_photos: int, passes: int) -> dict[str, Any]:
    ok = [c for c in calls if "error" not in c]
    s = [c["score"] for c in ok]
    fields = {
        "product_exact": _rate([x["product_exact"] for x in s]),
        "product_tolerant": _rate([x["product_tolerant"] for x in s]),
        "product_exact_in_catalogue_only": _rate([x["product_exact"] for x in s if x["in_catalogue"]]),
        "best_before_exact": _rate([x["date_exact"] for x in s]),
        "units_exact": _rate([x["units_exact"] for x in s]),
        "units_pm1": _rate([x["units_pm1"] for x in s]),
        "mrp_exact": _rate([x["mrp_exact"] for x in s if x["mrp_exact"] is not None]),
        "all_three_exact": _rate([not x["wrong"] for x in s]),
    }
    if not fields["mrp_exact"]["n"]:
        fields["mrp_exact"]["note"] = "not measurable: agents/capture/vision.py returns no mrp_inr field"
    times = [c["wall_s"] for c in ok]
    flagged = [x for x in s if x["needs_confirmation"]]
    unflagged = [x for x in s if x["needs_confirmation"] is False]
    date_low = [x for x in s if x.get("date_confidence") is not None and x["date_confidence"] < CONFIDENCE_THRESHOLD]
    date_high = [x for x in s if x.get("date_confidence") is not None and x["date_confidence"] >= CONFIDENCE_THRESHOLD]
    by_photo: dict[str, list[dict[str, Any]]] = {}
    for c in ok:
        by_photo.setdefault(c["file"], []).append(c)
    consistent = [
        len({(c["score"].get("predicted_sku"), (c["score"]["scored_row"] or {}).get("best_before_date"), c["score"].get("predicted_units")) for c in cs}) == 1
        for cs in by_photo.values() if len(cs) == passes
    ]
    return {
        "photos": n_photos, "passes": passes, "calls": len(calls), "errors": len(calls) - len(ok),
        "fields": fields,
        "latency_s": {"p50": percentile(times, 50), "p95": percentile(times, 95), "min": min(times, default=None),
                      "max": max(times, default=None), "two_pass_calls": sum(c["pass"] == "two_pass" for c in ok)},
        "consistency": {"photos_identical_across_all_passes": _rate(consistent)},
        "calibration": {
            "threshold": CONFIDENCE_THRESHOLD,
            "flagged_needs_confirmation": {"n": len(flagged), "actually_wrong": sum(x["wrong"] for x in flagged)},
            "not_flagged": {"n": len(unflagged), "actually_wrong": sum(x["wrong"] for x in unflagged)},
            "date_conf_below_threshold": {"n": len(date_low), "date_wrong": sum(not x["date_exact"] for x in date_low)},
            "date_conf_at_or_above_threshold": {"n": len(date_high), "date_wrong": sum(not x["date_exact"] for x in date_high)},
        },
    }


def worst(calls: list[dict[str, Any]], k: int = 5) -> list[dict[str, Any]]:
    """Worst photos (first pass): most fields wrong, ties broken by the most confident wrong read --
    a confident miss is worse for the UI than a flagged one."""
    first = [c for c in calls if c["pass_no"] == 1]

    def key(c: dict[str, Any]) -> tuple[int, float]:
        if "error" in c:
            return (4, 0.0)
        return (c["score"]["fields_wrong"] + (not c["score"]["needs_confirmation"] and c["score"]["wrong"]), c["score"]["min_confidence"] or 0.0)

    return sorted(first, key=key, reverse=True)[:k]


def run(dir_: Path, passes: int, store: LocalStore, backend: str | None = None) -> dict[str, Any]:
    labels = json.loads((dir_ / "labels.json").read_text(encoding="utf-8"))
    names = {p["sku"]: p["name"] for p in store.read("products")}
    calls = []
    for pass_no in range(1, passes + 1):
        for label in labels:
            data_url = "data:image/jpeg;base64," + base64.b64encode((dir_ / "photos" / label["file"]).read_bytes()).decode()
            t0 = time.perf_counter()
            try:
                res = intake(store, NODE_ID, image_data_url=data_url, backend=backend)
            except Exception as e:  # a failed call is a result, recorded, not a crash of the run
                calls.append({"file": label["file"], "pass_no": pass_no, "wall_s": round(time.perf_counter() - t0, 3), "error": f"{type(e).__name__}: {e}"})
                continue
            wall = round(time.perf_counter() - t0, 3)
            calls.append({"file": label["file"], "pass_no": pass_no, "wall_s": wall, "model_id": res.get("model_id"),
                          "pass": res.get("pass"), "raw_rows": res["rows"], "label": label, "score": score(label, res["rows"], names)})
            print(f"pass {pass_no} {label['file']}: {wall:.2f}s wrong={calls[-1]['score']['wrong']}", flush=True)
    return {"calls": calls, "summary": aggregate(calls, len(labels), passes), "worst": worst(calls)}


def _pct(r: dict[str, Any]) -> str:
    return f"{r['correct']}/{r['n']} ({r['rate']:.0%})" if r["n"] else "n/a"


def render(meta: dict[str, Any], s: dict[str, Any], worst_calls: list[dict[str, Any]]) -> str:
    f, cal, lat = s["fields"], s["calibration"], s["latency_s"]
    head = "measured" if meta["backend"] == "vertex" else "NOT A MEASUREMENT (backend is not vertex)"
    lines = [
        f"# Vision on real phone photos -- {head}",
        "",
        f"Generated by `python -m harness.vision_real_eval` at {meta['generated_at']}; backend `{meta['backend']}`, "
        f"model `{meta['model_id']}`; {s['photos']} photos x {s['passes']} passes = {s['calls']} calls, {s['errors']} errors. "
        "Every number below is recomputed from `results.json` in this directory. Rates are over all calls (photos x passes).",
        "",
        "| Field | Exact | Tolerant |",
        "|---|---|---|",
        f"| Product (normalised name) | {_pct(f['product_exact'])} | {_pct(f['product_tolerant'])} (token-subset) |",
        f"| Product, labelled product in demo catalogue only | {_pct(f['product_exact_in_catalogue_only'])} | |",
        f"| Best-before date | {_pct(f['best_before_exact'])} | |",
        f"| Units visible | {_pct(f['units_exact'])} | {_pct(f['units_pm1'])} (+-1) |",
        f"| MRP | {_pct(f['mrp_exact']) if f['mrp_exact']['n'] else f['mrp_exact'].get('note', 'n/a')} | |",
        f"| All three (product, date, units) | {_pct(f['all_three_exact'])} | |",
        "",
        f"Latency per `intake` call: p50 {lat['p50']} s, p95 {lat['p95']} s (min {lat['min']}, max {lat['max']}); "
        f"{lat['two_pass_calls']} call(s) took the second date-reading pass.",
        "",
        f"Consistency: {_pct(s['consistency']['photos_identical_across_all_passes'])} photos gave the same SKU, date and units on every pass.",
        "",
        f"## Confidence calibration (threshold {cal['threshold']})",
        "",
        "`needs_confirmation` is the flag the phone view uses to force a confirmation. A row is wrong if product, date or units is not exact.",
        "",
        f"- Flagged low-confidence: {cal['flagged_needs_confirmation']['n']} rows, {cal['flagged_needs_confirmation']['actually_wrong']} actually wrong.",
        f"- Not flagged (high-confidence, would commit without a question): {cal['not_flagged']['n']} rows, "
        f"**{cal['not_flagged']['actually_wrong']} actually wrong**.",
        f"- Date confidence < threshold: {cal['date_conf_below_threshold']['n']} rows, {cal['date_conf_below_threshold']['date_wrong']} dates wrong; "
        f">= threshold: {cal['date_conf_at_or_above_threshold']['n']} rows, {cal['date_conf_at_or_above_threshold']['date_wrong']} dates wrong.",
        "",
        "## Five worst photos (pass 1), with the model's raw rows",
        "",
    ]
    for c in worst_calls:
        lines.append(f"### {c['file']}")
        if "error" in c:
            lines += [f"Error: `{c['error']}`", ""]
            continue
        sc = c["score"]
        lab = c["label"]
        lines += [
            f"Label: {lab['product_name']}, best before {lab['best_before_date']}, {lab['units_visible']} units, MRP {lab['mrp_inr']}. "
            f"Scored: {sc['predicted_name']}, {(sc['scored_row'] or {}).get('best_before_date')}, {sc.get('predicted_units')} units; "
            f"fields wrong {sc['fields_wrong']}; flagged {sc['needs_confirmation']}; in catalogue {sc['in_catalogue']}.",
            "",
            "```json",
            json.dumps(c["raw_rows"], indent=1),
            "```",
            "",
        ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", required=True, help="directory written by harness.vision_real_prep")
    ap.add_argument("--passes", type=int, default=3)
    args = ap.parse_args(argv)
    dir_ = Path(args.dir)
    if not (dir_ / "labels.json").exists():
        print(f"no {dir_ / 'labels.json'}: run harness.vision_real_prep first", file=sys.stderr)
        return 2
    models = load_models()
    backend = models["backend"]
    out = run(dir_, args.passes, LocalStore(os.environ.get("TAAL_DATA_DIR", ".local/data")), backend)
    model_ids = sorted({c.get("model_id") for c in out["calls"] if c.get("model_id")})
    meta = {"generated_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
            "backend": backend, "model_id": ",".join(model_ids) or models["ids"]["flash"],
            "measurement": backend == "vertex", "confidence_threshold": CONFIDENCE_THRESHOLD, "node_id": NODE_ID}
    (dir_ / "results.json").write_text(json.dumps({"meta": meta, **out}, indent=1) + "\n", encoding="utf-8")
    (dir_ / "summary.md").write_text(render(meta, out["summary"], out["worst"]) + "\n", encoding="utf-8")
    print(f"wrote {dir_ / 'results.json'} and {dir_ / 'summary.md'}")
    return 0 if backend == "vertex" and not out["summary"]["errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
