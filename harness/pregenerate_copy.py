"""Pre-generate the demo plays' offer copy with BigQuery AI.GENERATE_TABLE and write it to the
committed fixture fixtures/copy_pregenerated.json (harness/seed_plays.py loads it onto the seeded
plays, so approve() reuses it instead of calling BigQuery on its 3 s path).

    GOOGLE_APPLICATION_CREDENTIALS=<key> GOOGLE_CLOUD_PROJECT=<project> TAAL_MODEL_BACKEND=vertex \
        uv run python -m harness.pregenerate_copy [--plays play_id ...] [--out PATH] [--dry-run]

Reads the seeded plays from $TAAL_DATA_DIR (run `make generate` first). For each demo play it calls
jobs.sense.copy.generate_copy_bigquery (timeout 60 s, after one throwaway warm-up call with a
300 s timeout, because the first call after the remote model is recreated can take minutes), then
passes every variant through jobs.sense.copy.validate_copy plus two extra checks: no number outside
the play's own facts, and distinct text within a language. A play with any slot missing or
rejected gets no fixture entry and keeps the templated path; generated text is never edited.
"""
from __future__ import annotations

import argparse
import copy as copylib
import json
import os
import re
import sys
import time
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from agents.gate.config import load_models
from agents.gate.store import LocalStore, load_catalogue
from harness.seed_plays import DEMO_GAPS
from jobs.sense.copy import _fmt_date, generate_copy_bigquery, validate_copy
from jobs.sense.copy_pregenerated import FIXTURE_PATH, METHOD, fingerprint

WARMUP_TIMEOUT_S = 300.0
CALL_TIMEOUT_S = 60.0
ATTEMPTS = 8
CHUNK = 2  # segments per BigQuery call
_NUM = re.compile(r"\d+(?:[.,]\d+)*")
# Claims the offer does not make. The prompt forbids them; this rejects a variant that makes one anyway.
_FALSE_CLAIMS = re.compile(r"\b(free|cart|gift|complimentary|guarantee[sd]?|moved)\b", re.IGNORECASE)


def allowed_numbers(play: dict[str, Any], best_before: str | None, partner_name: str = "", product_name: str = "") -> set[str]:
    """Digit runs a variant may contain: the play's own parameters and the best-before date in either form."""
    params = play.get("mechanic_params") or {}
    allowed: set[str] = set()
    for key in ("discount_pct", "markdown_pct", "bundle_price"):
        if params.get(key) is not None:
            allowed.add(f"{float(params[key]):g}")
    for text in (_fmt_date(best_before), best_before or "", partner_name, product_name):
        allowed.update(_NUM.findall(text))
    allowed.update(str(int(float(x))) for x in list(allowed) if re.fullmatch(r"\d+\.0+", x))
    return allowed


def slot_problems(v: dict[str, Any], play: dict[str, Any], best_before: str | None, product: dict[str, Any], partner: dict[str, Any] | None) -> list[str]:
    """Why one variant cannot be stored: validate_copy (sell-by disclosure, discount) and no number
    outside the play's own facts."""
    accepted, reasons = validate_copy([v], play, best_before)
    problems = list(reasons) if reasons else ([] if accepted else ["validate_copy dropped the variant"])
    allowed = allowed_numbers(play, best_before, (partner or {}).get("name", ""), product["name"])
    extra = [n for n in _NUM.findall(v["text"]) if n not in allowed]
    if extra:
        problems.append(f"{v['segment_id']}/{v['language']}: numbers not in the play's facts: {extra}")
    claim = _FALSE_CLAIMS.search(v["text"])
    if claim:
        problems.append(f"{v['segment_id']}/{v['language']}: claims the offer does not make: {claim.group(0)!r}")
    if play["mechanic"] == "bundle" and v["language"] == "en" and partner and partner.get("name"):
        head = re.sub(r"[^A-Za-z ]", " ", partner["name"]).split()
        if head and head[0].lower() not in v["text"].lower():
            problems.append(f"{v['segment_id']}/{v['language']}: bundle text does not name the partner product {partner['name']!r}")
    return problems


def check_variants(variants: list[dict[str, Any]], play: dict[str, Any], best_before: str | None, product: dict[str, Any], partner: dict[str, Any] | None) -> list[str]:
    """Why these variants cannot be stored, or [] when they can: every (segment, language) slot
    present, every variant passes slot_problems, and distinct text per language."""
    problems: list[str] = []
    expected = {(s, lang) for s in play["audience"]["segment_ids"] for lang in play["copy"]["language_set"]}
    got = [(v["segment_id"], v["language"]) for v in variants]
    if set(got) != expected or len(got) != len(expected):
        problems.append(f"slots: expected {len(expected)}, got {len(got)} ({sorted(expected - set(got))[:3]} missing)")
    for v in variants:
        problems.extend(slot_problems(v, play, best_before, product, partner))
    for lang in play["copy"]["language_set"]:
        texts = [v["text"].strip().lower() for v in variants if v["language"] == lang]
        if len(set(texts)) != len(texts):
            problems.append(f"{lang}: {len(texts) - len(set(texts))} duplicate line(s)")
    return problems


def _generate_one(play: dict[str, Any], product: dict[str, Any], partner: dict[str, Any] | None, best_before: str | None, project: str, region: str, model_id: str, timeout_s: float = CALL_TIMEOUT_S) -> tuple[list[dict[str, Any]] | None, list[str]]:
    """Fill the play's (segment, language) slots over up to ATTEMPTS rounds of BigQuery calls. The
    open slots are requested CHUNK segments at a time: a call either returns in a few seconds or
    stalls until its timeout, so small calls lose less to a stall. A slot that passed the checks is
    kept; later rounds ask only for the slots still open. Returns (variants in slot order, [])
    when every slot is filled with distinct text, else (None, why)."""
    segs, langs = list(play["audience"]["segment_ids"]), list(play["copy"]["language_set"])
    won: dict[tuple[str, str], dict[str, Any]] = {}
    problems: list[str] = []
    for attempt in range(1, ATTEMPTS + 1):
        open_segs = [s for s in segs if any((s, lang) not in won for lang in langs)]
        if not open_segs:
            break
        for i in range(0, len(open_segs), CHUNK):
            chunk = open_segs[i : i + CHUNK]
            open_slots = {(s, lang) for s in chunk for lang in langs if (s, lang) not in won}
            work = copylib.deepcopy(play)
            work["audience"]["segment_ids"] = chunk
            work["copy"]["language_set"] = [lang for lang in langs if any((s, lang) in open_slots for s in chunk)]
            t0 = time.perf_counter()
            try:
                got = generate_copy_bigquery(work, product, best_before, work["copy"]["language_set"], project=project, region=region, model_id=model_id, timeout_s=timeout_s, angle_order=segs, partner_name=(partner or {}).get("name"))
            except Exception as e:  # a stall or failure: the slots stay open for the next round
                problems = [f"round {attempt}: BigQuery call failed: {type(e).__name__}: {str(e)[:200]}"]
                print(f"  round {attempt} {chunk}: failed after {time.perf_counter() - t0:.1f}s: {type(e).__name__}")
                continue
            problems = []
            for v in got:
                slot = (v["segment_id"], v["language"])
                if slot not in open_slots:
                    continue
                bad = slot_problems(v, play, best_before, product, partner)
                taken = {w["text"].strip().lower() for (_, lang), w in won.items() if lang == v["language"]}
                if bad:
                    problems.extend(bad)
                elif v["text"].strip().lower() in taken:
                    problems.append(f"{slot[0]}/{slot[1]}: duplicate of another line")
                else:
                    won[slot] = {k: v[k] for k in ("segment_id", "language", "text", "disclosure_included")}
            print(f"  round {attempt} {chunk}: {len(got)} returned in {time.perf_counter() - t0:.1f}s, {len(won)}/{len(segs) * len(langs)} slots filled, {len(problems)} rejected")
            for pr in problems[:3]:
                print(f"    rejected: {pr[:200]}")
    if len(won) < len(segs) * len(langs):
        return None, problems or ["slots not filled"]
    variants = [won[(s, lang)] for s in segs for lang in langs]
    final = check_variants(variants, play, best_before, product, partner)
    return (variants, []) if not final else (None, final)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--data", default=os.environ.get("TAAL_DATA_DIR", ".local/data"))
    ap.add_argument("--out", default=str(FIXTURE_PATH))
    ap.add_argument("--plays", nargs="*", help="play ids to generate (default: every seeded demo play)")
    ap.add_argument("--timeout", type=float, default=CALL_TIMEOUT_S, help="per-call timeout in seconds (default 60)")
    ap.add_argument("--dry-run", action="store_true", help="generate and report, do not write the fixture")
    args = ap.parse_args(argv)

    models = load_models()
    if models["backend"] != "vertex":
        print("pregenerate_copy: needs TAAL_MODEL_BACKEND=vertex (and GOOGLE_CLOUD_PROJECT)", file=sys.stderr)
        return 2
    project = os.environ.get(models["vertex"]["project_env"])
    if not project:
        print(f"pregenerate_copy: {models['vertex']['project_env']} is not set", file=sys.stderr)
        return 2
    region, model_id = models["vertex"]["location"], models["ids"]["flash"]

    store = LocalStore(args.data)
    catalogue = load_catalogue(store)
    out_path = Path(args.out)
    entries: dict[str, Any] = {}
    if out_path.exists():
        try:
            entries = json.loads(out_path.read_text(encoding="utf-8"))
        except ValueError:
            entries = {}

    plays = []
    for gap_id in DEMO_GAPS:
        for row in store.find("plays", gap_id=gap_id):
            plays.append(json.loads(row["play_json"]))
    if args.plays:
        plays = [p for p in plays if p["play_id"] in set(args.plays)]
    if not plays:
        print("pregenerate_copy: no seeded plays found (run `make generate`)", file=sys.stderr)
        return 2

    # Warm the remote model with one throwaway single-slot call: the first call after the model is
    # recreated (every deploy does that) can take minutes.
    first = copylib.deepcopy(plays[0])
    first["audience"]["segment_ids"] = first["audience"]["segment_ids"][:1]
    first["copy"]["language_set"] = ["en"]
    gap0 = store.find("gaps", gap_id=first["gap_id"])[-1]
    t0 = time.perf_counter()
    try:
        generate_copy_bigquery(first, catalogue[first["target"]["sku"]], gap0["evidence"].get("expiry_date"), ["en"], project=project, region=region, model_id=model_id, timeout_s=WARMUP_TIMEOUT_S)
        print(f"warm-up: ok in {time.perf_counter() - t0:.1f}s")
    except Exception as e:
        print(f"warm-up: failed after {time.perf_counter() - t0:.1f}s: {type(e).__name__}: {str(e)[:200]}")

    failures: dict[str, list[str]] = {}
    for play in plays:
        pid = play["play_id"]
        gap = store.find("gaps", gap_id=play["gap_id"])[-1]
        best_before = gap["evidence"].get("expiry_date")
        product = catalogue[play["target"]["sku"]]
        partner = catalogue.get((play.get("mechanic_params") or {}).get("bundle_sku") or "")
        print(f"{pid} ({play['mechanic']}, {len(play['audience']['segment_ids'])} segment(s) x {play['copy']['language_set']})")
        variants, problems = _generate_one(play, product, partner, best_before, project, region, model_id, args.timeout)
        entries.pop(pid, None)  # a stale entry must never outlive a failed regeneration
        if variants is None:
            failures[pid] = problems
            print(f"  NOT stored, templated path kept: {problems[:3]}")
            continue
        entries[pid] = {
            "generated_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
            "model": model_id, "location": region, "method": METHOD,
            "fingerprint": fingerprint(play, best_before), "best_before": best_before,
            "variants": [{k: v[k] for k in ("segment_id", "language", "text", "disclosure_included")} for v in variants],
        }
        print(f"  stored {len(variants)} variant(s)")

    if not args.dry_run:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(dict(sorted(entries.items())), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {out_path} ({len(entries)} play(s))")
    print(f"summary: stored {len(entries)}, templated path kept for {sorted(failures)} (as of {date.today()})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
