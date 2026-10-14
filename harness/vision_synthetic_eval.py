"""Re-read the 30 staged synthetic warehouse photos through the served vision path and score the dates.

    TAAL_MODEL_BACKEND=vertex GOOGLE_CLOUD_PROJECT=amru-509214 GOOGLE_APPLICATION_CREDENTIALS=... \\
      uv run python -m harness.vision_synthetic_eval --out eval/raw/vision_synthetic_<date>.json [--cap-usd 1.0]

Same method as the 21 Sep 2026 card (eval/raw/vision_synthetic_2026-09-21.json, whose planted ground
truth per SKU this reads): each photo in fixtures/photos/synthetic_vision_test/<SKU>.jpg goes to
`agents.capture.vision.intake` as an uploaded data URL, the function POST /capture calls for an upload.
One pass per photo. A photo scores `date_correct` when the row for that SKU (else the highest
confidence row) carries the planted date, and `pass_at_threshold` when it is also at confidence >=
CONFIDENCE_THRESHOLD. Every photo is Gemini-generated and synthetic; this is a self-test of the
pipeline on legible renders, not accuracy on real phone photos.

Each call's model id (`model_id` in the intake result, the model that actually answered) and token
usage are recorded beside the scores, and the run aborts before a call that could take its own
spend past --cap-usd. The result file is INVALID if any model_id differs from the configured flash.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from agents.capture import vision
from agents.capture.vision import CONFIDENCE_THRESHOLD, intake
from agents.gate.config import load_models
from agents.gate.store import LocalStore
from harness.checklists import ROOT

PHOTOS = ROOT / "fixtures" / "photos" / "synthetic_vision_test"
TRUTH = ROOT / "eval" / "raw" / "vision_synthetic_2026-09-21.json"
NODE_ID = "DS-07"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True)
    ap.add_argument("--cap-usd", type=float, default=1.0)
    args = ap.parse_args(argv)
    models = load_models()
    backend = models["backend"]
    if backend != "vertex":
        print("vision_synthetic_eval: needs TAAL_MODEL_BACKEND=vertex; nothing run")
        return 1
    pr = models["pricing"]
    uin, uout, disc = pr["usd_per_million_input"] / 1e6, pr["usd_per_million_output"] / 1e6, pr["cached_input_discount"]
    flash = models["ids"]["flash"]
    usage_log: list[dict] = []
    spent = {"usd": 0.0}
    orig = vision.generate_with_failover

    def tapped(models_, contents, config, start=None, thinking_level=None):
        if spent["usd"] + 0.05 >= args.cap_usd:
            print(f"vision_synthetic_eval: spend cap {args.cap_usd} reached ({spent['usd']:.4f}); stopping")
            raise SystemExit(42)
        resp, used = orig(models_, contents, config, start=start, thinking_level=thinking_level)
        um = resp.usage_metadata
        u = {"prompt": int(um.prompt_token_count or 0), "candidates": int(um.candidates_token_count or 0),
             "thoughts": int(um.thoughts_token_count or 0), "cached": int(um.cached_content_token_count or 0)}
        usd = (u["prompt"] - u["cached"]) * uin + u["cached"] * uin * (1 - disc) + (u["candidates"] + u["thoughts"]) * uout
        spent["usd"] += usd
        usage_log.append({"model_answered": used, "model_version": getattr(resp, "model_version", None), "usage": u, "usd": round(usd, 6)})
        return resp, used

    vision.generate_with_failover = tapped
    truth = json.loads(TRUTH.read_text(encoding="utf-8"))
    store = LocalStore(os.environ.get("TAAL_DATA_DIR", ".local/data"))
    results, models_seen = [], set()
    t0 = time.time()
    for t in truth:
        photo = PHOTOS / f"{t['sku']}.jpg"
        data_url = "data:image/jpeg;base64," + base64.b64encode(photo.read_bytes()).decode()
        before = len(usage_log)
        res = intake(store, NODE_ID, image_data_url=data_url, backend=backend)
        models_seen.add(res.get("model_id"))
        rows = res["rows"]
        row = next((r for r in rows if r["sku_guess"] == t["sku"]), None) or max(rows, key=lambda r: r["date_confidence"])
        ok = row["best_before_date"] == t["true_best_before"]
        results.append({
            "sku": t["sku"], "name": t["name"], "true_best_before": t["true_best_before"], "true_facings": t["true_facings"],
            "predicted_best_before": row["best_before_date"], "date_confidence": row["date_confidence"],
            "predicted_facings": row.get("facings_count"), "date_correct": ok,
            "pass_at_threshold": ok and row["date_confidence"] >= CONFIDENCE_THRESHOLD, "n_rows": len(rows),
            "sku_guess": row["sku_guess"], "model_id": res.get("model_id"), "model_calls": len(usage_log) - before,
        })
        print(f"  {t['sku']:34s} {'OK ' if ok else 'MISS'} {row['best_before_date']} conf={row['date_confidence']}", flush=True)
    n = len(results)
    summary = {
        "measured_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "configured_model": flash,
        "models_that_answered": sorted(m for m in models_seen if m),
        "valid_all_answered_by_configured_model": models_seen == {flash},
        "photos": n,
        "date_correct": sum(r["date_correct"] for r in results),
        "pass_at_threshold": sum(r["pass_at_threshold"] for r in results),
        "confidence_threshold": CONFIDENCE_THRESHOLD,
        "model_calls": len(usage_log),
        "usage": {k: sum(u["usage"][k] for u in usage_log) for k in ("prompt", "candidates", "thoughts", "cached")},
        "usd_at_config_list_prices": round(spent["usd"], 4),
        "wall_s": round(time.time() - t0, 1),
        "label": "SYNTHETIC: Gemini-generated photos, self-tested; not a measure of accuracy on real phone photos",
    }
    Path(args.out).write_text(json.dumps({"summary": summary, "photos": results, "calls": usage_log}, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
